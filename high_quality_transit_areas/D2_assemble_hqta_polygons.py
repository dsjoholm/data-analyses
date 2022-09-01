"""
Make a polygon version of HQ transit corridors for open data portal.

From combine_and_visualize.ipynb
"""
import dask.dataframe as dd
import dask_geopandas as dg
import datetime as dt
import geopandas as gpd
import pandas as pd
import sys

from loguru import logger

import C1_prep_for_clipping as prep_clip
import D1_assemble_hqta_points as assemble_hqta_points
import utilities
from shared_utils import utils, geography_utils
from D1_assemble_hqta_points import EXPORT_PATH
from update_vars import analysis_date

logger.add("./logs/D2_assemble_hqta_polygons.log")
logger.add(sys.stderr, 
           format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}", 
           level="INFO")

HQTA_POINTS_FILE = utilities.catalog_filepath("hqta_points")

## drop incorrect HMB data, TODO investigate
## drop incorrect Cheviot data, TODO investigate refactor (run shapes in frequency order...)
bad_stops = ['315604', '315614', '689']


def filter_and_buffer(hqta_points: dg.GeoDataFrame, 
                      hqta_segments: dg.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Convert the HQTA point geom into polygon geom.
    
    Buffers are already drawn for corridors and stops, so 
    draw new buffers, and address each hqta_type separately.
    """
    stops = (hqta_points[hqta_points.hqta_type != "hq_corridor_bus"]
             .to_crs(geography_utils.CA_NAD83Albers)
            )
    
    corridors = hqta_segments.to_crs(geography_utils.CA_NAD83Albers)
    
    # General buffer distance: 1/2mi ~= 805 meters
    # Bus corridors are already buffered 50 meters, so will buffer 755 meters
    stops = stops.assign(
        geometry = stops.geometry.buffer(805)
    )
    
    corridor_cols = [
        "calitp_itp_id_primary", "stop_id", "hqta_segment_id", 
        "am_max_trips", "pm_max_trips", 
        "hqta_type", "geometry"
    ]
    
    corridors = corridors.assign(
        geometry = corridors.geometry.buffer(755),
        # overwrite hqta_type for this polygon
        hqta_type = "hq_corridor_bus",
        calitp_itp_id_primary = corridors.calitp_itp_id.astype(int),
    )[corridor_cols]
    
    hqta_polygons = (dd.multi.concat([corridors, stops], axis=0)
                     .to_crs(geography_utils.WGS84)
                     # Make sure dtype is still int after concat
                     .astype({"calitp_itp_id_primary": int})
                    ).compute()
    
    return hqta_polygons


def drop_bad_stops_final_processing(gdf: gpd.GeoDataFrame, 
                                    bad_stop_list: list) -> gpd.GeoDataFrame:
    """
    Input a list of known bad stops in the script to 
    exclude from the polygons.
    """
    keep_cols = [
        "calitp_itp_id_primary", "calitp_itp_id_secondary", 
        "agency_name_primary", "agency_name_secondary",
        "hqta_type", "hqta_details", "geometry"
    ]
    
    # Drop bad stops, subset columns
    gdf2 = (gdf[~gdf.stop_id.isin(bad_stop_list)]
            [keep_cols]
            .sort_values(["hqta_type", "calitp_itp_id_primary", 
                          "calitp_itp_id_secondary",
                          "hqta_details"])
            .reset_index(drop=True)
           )
    
    return gdf2


if __name__=="__main__":
    logger.info(f"Analysis date: {analysis_date}")
    start = dt.datetime.now()
    
    hqta_points = dg.read_parquet(HQTA_POINTS_FILE)
    bus_hq_corr = prep_clip.prep_bus_corridors()
    
    # Filter and buffer for stops (805 m) and corridors (755 m)
    # and add agency_names
    gdf = filter_and_buffer(hqta_points, bus_hq_corr)
    
    time1 = dt.datetime.now()
    logger.info(f"filter and buffer: {time1 - start}")
    
    # Drop bad stops, subset, get ready for export
    gdf2 = drop_bad_stops_final_processing(gdf, bad_stops)    
    
    # Export to GCS
    # Stash this date's into its own folder, to convert to geojson, geojsonl
    utils.geoparquet_gcs_export(gdf2, 
                                EXPORT_PATH, 
                                'ca_hq_transit_areas'
                               )
    
    # Overwrite most recent version (other catalog entry constantly changes)
    utils.geoparquet_gcs_export(gdf2,
                                utilities.GCS_FILE_PATH,
                                'hqta_areas'
                               )    
        
    end = dt.datetime.now()
    logger.info(f"execution time: {end-start}")