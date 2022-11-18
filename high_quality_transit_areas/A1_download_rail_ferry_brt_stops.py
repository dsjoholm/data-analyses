"""
Download rail, ferry, BRT stops.

From rail_ferry_brt.ipynb into script.
"""
import os
os.environ["CALITP_BQ_MAX_BYTES"] = str(200_000_000_000)

import dask.dataframe as dd
import dask_geopandas as dg
import geopandas as gpd
import pandas as pd

from siuba import *

from update_vars import analysis_date, COMPILED_CACHED_VIEWS


def trip_keys_for_route_type(analysis_date: str, 
                             route_type_list: list) -> pd.DataFrame: 
    """
    Subset the trips table for specified route types.
    Keep route info (route_id, route_type) that's needed.
    """
    trips = dd.read_parquet(
        f"{COMPILED_CACHED_VIEWS}trips_{analysis_date}.parquet")
    
    # Choose to output df instead of list because we need route_type later on
    trip_keys_for_type = (trips[trips.route_type.isin(route_type_list)]
                          [["trip_key", "route_id", "route_type"]]
                          .drop_duplicates()
                          .compute()
                         )
    
    return trip_keys_for_type


def trip_keys_to_stop_ids(trip_key_df: pd.DataFrame) -> dd.DataFrame:
    """
    Use the cached stop times table to avoid running query with the 
    tbls.index. This function is called in `grab_stops`.
    
    Keep the subset of trips we're interested in based on route_type 
    filter in the stop_times table.
    
    Only keep unique stop_id combo. 
    """
    stop_times = dd.read_parquet(
        f"{COMPILED_CACHED_VIEWS}st_{analysis_date}.parquet")
        
    # Do a merge to narrow down stop_ids based on trip_keys
    # Keep unique stop (instead of stop_time combo)
    # and also retain route type that came from trip_key_df
    keep_cols = ["calitp_itp_id", "stop_id", "route_id", "route_type"]
    
    stop_ids_present = dd.merge(
        stop_times[stop_times.trip_key.isin(trip_key_df.trip_key)],
        trip_key_df,
        on = ["trip_key"],
        how = "inner"
    )[keep_cols].drop_duplicates()
    
    return stop_ids_present


def grab_stops(analysis_date: str, 
               trip_key_df: pd.DataFrame) -> gpd.GeoDataFrame:
    """
    Merge stops table to get point geom attached to stop_ids 
    for specified route_types.
    """
    stops = dg.read_parquet(
        f"{COMPILED_CACHED_VIEWS}stops_{analysis_date}.parquet")
    
    # Based on subset of trips, grab the stop_ids present.
    stops_present = trip_keys_to_stop_ids(trip_key_df)
    
    # merge stops table and get point geom
    stops_for_route_type = (
        dd.merge(
            stops,
            stops_present,
            on = ["calitp_itp_id", "stop_id"],
            how = "inner"
        ).drop_duplicates()
        .reset_index(drop=True)
        .compute()
    )
    
    return stops_for_route_type
    

def grab_rail_data(analysis_date: str) -> gpd.GeoDataFrame:
    """
    Grab all the rail routes by subsetting routes table down to certain route types.
    
    Combine it routes with stop point geom.
    Returns gpd.GeoDataFrame.
    """
    # Grab the different route types for rail from route tables
    rail_route_types = ['0', '1', '2']
    
    # Grab trip_keys associated with this route_type
    rail_trip_keys = trip_keys_for_route_type(analysis_date, rail_route_types)
        
    rail_stops = grab_stops(analysis_date, rail_trip_keys)
        
    rail_stops.to_parquet("./data/rail_stops.parquet")
    

def grab_operator_brt_NEW(analysis_date: str) -> gpd.GeoDataFrame:

    trips = dd.read_parquet(
        f"{COMPILED_CACHED_VIEWS}trips_{analysis_date}.parquet")
    
    BRT_ROUTE_FILTERING = {
        # LA Metro BRT
        182: {"route_desc": ["METRO SILVER LINE", "METRO ORANGE LINE"]},
              #["901", "910"]
        # AC Transit BRT
        4: {"route_id": ['1T']},
        # Omni BRT -- too infrequent!
        #232: {"route_short_name": ['sbX']},
        # Muni
        282: {"route_short_name": ['49']}
    }
    
    BRT_OPERATORS = list(BRT_ROUTE_FILTERING.keys())
    operator_trips = trips[trips.calitp_itp_id.isin(BRT_OPERATORS)]
    
    # Set metadata for dask
    all_brt_trips = operator_trips.head(0)
    
    for itp_id, filtering_cond in BRT_ROUTE_FILTERING.items():
        trips_subset = operator_trips[operator_trips.calitp_itp_id==itp_id]
        
        for col, filtering_list in filtering_cond.items():
            operator_brt = trips_subset[trips_subset[col].isin(filtering_list)]
        
        all_brt_trips = dd.multi.concat([all_brt_trips, operator_brt], axis=0)
    
    
    # Grab trip_keys associated with this operator's BRT routes
    brt_trip_keys = (all_brt_trips[["trip_key", "route_id", "route_type"]]
                     .drop_duplicates()
                     .compute()
                    )
        
    brt_stops = grab_stops(analysis_date, brt_trip_keys)
    
    brt_stops.to_parquet("./data/brt_stops.parquet")



def grab_operator_brt(itp_id: int, analysis_date: str):
    """
    Grab BRT routes, stops data for certain operators in CA by analysis date.
    """
        
    trips = dd.read_parquet(
        f"{COMPILED_CACHED_VIEWS}trips_{analysis_date}.parquet")
    
    operator_trips = trips[trips.calitp_itp_id==itp_id]
    
    # Filter within specific operator, each operator has specific filtering condition
    # If it's not one of the ones listed, raise an error
    BRT_OPERATORS = [
        182, 4, 282, 
        # 232, # Omni BRT too infrequent 
    ]
    

    
    col, filtering_list = list(BRT_ROUTE_FILTERING[itp_id].items())[0]     
    brt_trips = operator_trips[operator_trips[col].isin(filtering_list)]
        
    # Grab trip_keys associated with this operator's BRT routes
    brt_trip_keys = (brt_trips[["trip_key", "route_id", "route_type"]]
                     .drop_duplicates()
                     .compute()
                    )
        
    brt_stops = grab_stops(analysis_date, brt_trip_keys)
        
    if itp_id not in BRT_OPERATORS:
        raise KeyError("Operator does not have BRT route filtering condition set.")
    
    brt_stops.to_parquet(f"./data/brt_stops_{itp_id}.parquet")


def additional_brt_filtering_out_stops(df: gpd.GeoDataFrame, 
                                       itp_id: int, 
                                       filtering_list: list) -> gpd.GeoDataFrame:
    """
    df: geopandas.GeoDataFrame
        Input BRT stops data
    itp_id: int
    filtering_list: list of stop_ids
    """
    if itp_id == 182:
        brt_df_stops = df >> filter(-_.stop_id.isin(filtering_list))
        
    elif itp_id == 282:
        brt_df_stops = df >> filter(_.stop_id.isin(filtering_list))
    
    return brt_df_stops


def grab_ferry_data(analysis_date: str):
    ferry_route_types = ['4']
    
    # Grab trip_keys associated with this route_type
    ferry_trip_keys = trip_keys_for_route_type(analysis_date, ferry_route_types)
    
    ferry_stops = grab_stops(analysis_date, ferry_trip_keys)
        
    # TODO: only stops without bus service, implement algorithm
    angel_and_alcatraz = ['2483552', '2483550', '43002'] 
    
    ferry_stops = ferry_stops >> filter(-_.stop_id.isin(angel_and_alcatraz))
    
    ferry_stops.to_parquet("./data/ferry_stops.parquet")
