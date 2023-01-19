"""
Download all stops for a day.
"""
import os
os.environ["CALITP_BQ_MAX_BYTES"] = str(200_000_000_000)

import datetime as dt
import pandas as pd
import sys 

from loguru import logger

import operators_for_hqta
from shared_utils import gtfs_utils_v2, geography_utils, utils
from update_vars import analysis_date, COMPILED_CACHED_VIEWS

if __name__ == "__main__":
    #from dask.distributed import Client
    
    #client = Client("dask-scheduler.dask.svc.cluster.local:8786")
    
    logger.add("./logs/download_data.log", retention="3 months")
    logger.add(sys.stderr, 
               format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}", 
               level="INFO")
    
    logger.info(f"Analysis date: {analysis_date}")
    start = dt.datetime.now()
    
    hqta_operators_df = operators_for_hqta.scheduled_operators_for_hqta(
        analysis_date)
    
    FEEDS_TO_RUN = sorted(hqta_operators_df.feed_key.unique().tolist())    
    
    logger.info(f"# operators to run: {len(FEEDS_TO_RUN)}")
    
    dataset = "stops"
    logger.info(f"*********** Download {dataset} data ***********")

  
    # keep all the route_types, use for filtering for rail/brt/ferry later
    route_type_vals = [0, 1, 2, 3, 4, 5, 6, 7, 11, 12]
    route_type_cols = [f"route_type_{i}" for i in route_type_vals] 
    
    keep_stop_cols = [
        "feed_key",
        "stop_id", "stop_key", "stop_name", 
    ] + route_type_cols + ["missing_route_type"]

    
    stops = gtfs_utils_v2.get_stops(
        selected_date = analysis_date,
        operator_feeds = FEEDS_TO_RUN,
        stop_cols = keep_stop_cols,
        get_df = True,
        crs = geography_utils.CA_NAD83Albers,
    )
    
    utils.geoparquet_gcs_export(
        stops, 
        COMPILED_CACHED_VIEWS,
        f"{dataset}_{analysis_date}.parquet"
    )
    
    end = dt.datetime.now()
    logger.info(f"execution time: {end-start}")
