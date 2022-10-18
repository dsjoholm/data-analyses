"""
Functions to query GTFS schedule data, 
save locally as parquets, 
then clean up at the end of the script.
"""
import os
os.environ["CALITP_BQ_MAX_BYTES"] = str(130_000_000_000)

import dask.dataframe as dd
import dask_geopandas as dg
import datetime
import geopandas as gpd
import pandas as pd

from siuba import *

from shared_utils import geography_utils, gtfs_utils, utils, rt_dates

ANALYSIS_DATE = gtfs_utils.format_date(rt_dates.DATES["oct2022"])

GCS = "gs://calitp-analytics-data/data-analyses/"
TRAFFIC_OPS_GCS = f"{GCS}traffic_ops/"
COMPILED_CACHED_GCS = f"{GCS}rt_delay/compiled_cached_views/"
DATA_PATH = "./data/"

def grab_amtrak(selected_date: datetime.date | str
               ) -> tuple[gpd.GeoDataFrame, pd.DataFrame, gpd.GeoDataFrame]:
    """
    Amtrak (ITP_ID 13) is always excluded from queries for hqta and rt_delay
    
    Add back in now for our open data portal dataset
    """
    itp_id = 13
    
    keep_stop_cols = [
        'calitp_itp_id', 'stop_id', 'stop_name', 
        'stop_lon', 'stop_lat', 'stop_key'
    ]
    
    amtrak_stops = gtfs_utils.get_stops(
        selected_date = selected_date, 
        itp_id_list = [itp_id],
        stop_cols = keep_stop_cols,
        get_df = True,
        crs = geography_utils.CA_NAD83Albers, # this is the CRS used for rt_delay
    )
    
    amtrak_stops.to_parquet("amtrak_stops.parquet")
    
    keep_trip_cols = [
        'calitp_itp_id', 'calitp_url_number', 'service_date', 'trip_key',
        'trip_id', 'route_id', 'direction_id', 'shape_id',
        'calitp_extracted_at', 'calitp_deleted_at', 
    ]
    
    amtrak_trips = gtfs_utils.get_trips(
        selected_date = selected_date, 
        itp_id_list = [itp_id],
        trip_cols = keep_trip_cols,
        get_df = False,
    )
    
    # Grab route_info, return LazyTbl, and merge with trips
    keep_route_cols = [
        'calitp_itp_id', 'route_id',
        'route_short_name',
        'route_long_name', 'route_desc', 'route_type'
    ]

    amtrak_route_info = gtfs_utils.get_route_info(
        selected_date = selected_date,
        itp_id_list = [itp_id],
        route_cols = keep_route_cols,
        get_df = False
    )
    
    amtrak_trips = (amtrak_trips 
         >> inner_join(_, amtrak_route_info, 
                       on = ['calitp_itp_id', 'route_id'])
         >> collect()
        )
    
    amtrak_trips.to_parquet("amtrak_trips.parquet")
    
    amtrak_routelines = gtfs_utils.get_route_shapes(
        selected_date = selected_date,
        itp_id_list = [itp_id],
        get_df = True,
        crs = geography_utils.CA_NAD83Albers,
        trip_df = amtrak_trips
    )
    
    amtrak_routelines.to_parquet("amtrak_routelines.parquet")
    
    amtrak_st = gtfs_utils.get_stop_times(
        selected_date = selected_date,
        itp_id_list = [itp_id],
        get_df = True,
        trip_df = amtrak_trips
    )
    
    amtrak_st.to_parquet("amtrak_st.parquet")


def concatenate_amtrak(
    selected_date: datetime.date | str = "2022-05-04", 
    export_path: str = COMPILED_CACHED_GCS):
    """
    Grab the cached file on selected date for trips, stops, routelines.
    Concatenate Amtrak.
    Save a new cached file in GCS.
    """
    date_str = gtfs_utils.format_date(selected_date)
    
    amtrak_trips = dd.read_parquet("amtrak_trips.parquet")
    amtrak_routelines = dg.read_parquet("amtrak_routelines.parquet")
    amtrak_stops = dg.read_parquet("amtrak_stops.parquet")
    amtrak_st = dd.read_parquet("amtrak_st.parquet")
    
    
    trips = dd.read_parquet(f"{export_path}trips_{date_str}.parquet")
    trips_all = (dd.multi.concat([trips, amtrak_trips], axis=0)
                 .astype({"trip_key": int})
                 .drop_duplicates()
                 .reset_index()
                )
    trips_all.compute().to_parquet(f"{export_path}trips_{date_str}_all.parquet")
    
    stops = dg.read_parquet(f"{export_path}stops_{date_str}.parquet")
    stops_all = (dd.multi.concat([
                stops.to_crs(geography_utils.WGS84), 
                amtrak_stops.to_crs(geography_utils.WGS84)], axis=0)
            .astype({"stop_key": "Int64"})
            .drop_duplicates()
            .reset_index()
    ).compute()
    utils.geoparquet_gcs_export(stops_all, export_path, f"stops_{date_str}_all")
        
    routelines = dg.read_parquet(f"{export_path}routelines_{date_str}.parquet")        
    routelines_all = (dd.multi.concat([
                        routelines.to_crs(geography_utils.WGS84), 
                        amtrak_routelines.to_crs(geography_utils.WGS84)], axis=0)
                      .astype({"trip_key": "Int64"})
                      .drop_duplicates()
                      .reset_index()
                ).compute()
    utils.geoparquet_gcs_export(routelines_all, 
                                export_path, f"routelines_{date_str}_all")
    
    st = dd.read_parquet(f"{export_path}st_{date_str}.parquet")
    st_all = (dd.multi.concat([
                st, amtrak_st], axis=0)
              .astype({"stop_time_key": "Int64", 
                       "trip_key": "Int64"})
              .drop_duplicates()
              .reset_index()
    )
    st_all.compute().to_parquet(f"{export_path}st_{date_str}_all.parquet")
    
    # Remove Amtrak now that full dataset made
    for dataset in ["trips", "routelines", "stops", "st"]:
        os.remove(f"amtrak_{dataset}.parquet")


def create_local_parquets(selected_date):
    grab_amtrak(selected_date)
    concatenate_amtrak(selected_date, COMPILED_CACHED_GCS)

        
#----------------------------------------------------#        
# Functions are used in 
# `create_routes_data.py` and `create_stops_data.py`
#----------------------------------------------------#
# Define column names, must fit ESRI 10 character limits
RENAME_COLS = {
    "calitp_itp_id": "itp_id",
    "calitp_agency_name": "agency",
    "route_name_used": "route_name",
}