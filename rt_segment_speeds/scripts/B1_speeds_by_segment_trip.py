"""
Do linear referencing by segment-trip 
and derive speed.
"""
import os
os.environ['USE_PYGEOS'] = '0'

import dask.dataframe as dd
import datetime
import pandas as pd
import sys

from dask import delayed
from loguru import logger

from shared_utils import dask_utils
from segment_speed_utils import helpers, segment_calcs, wrangle_shapes
from segment_speed_utils.project_vars import (SEGMENT_GCS, analysis_date, 
                                              CONFIG_PATH)    
    
def linear_referencing_and_speed_by_segment(
    analysis_date: str,
    dict_inputs: dict = {}
):
    """
    With just enter / exit points on segments, 
    do the linear referencing to get shape_meters, and then derive speed.
    """
    time0 = datetime.datetime.now()    
    
    VP_FILE = dict_inputs["stage3"]
    SEGMENT_FILE = dict_inputs["segments_file"]
    SEGMENT_IDENTIFIER_COLS = dict_inputs["segment_identifier_cols"]
    TIMESTAMP_COL = dict_inputs["timestamp_col"]    
    EXPORT_FILE = dict_inputs["stage4"]
    
    # Keep subset of columns - don't need it all. we can get the 
    # columns dropped through segments file
    vp_keep_cols = [
        'gtfs_dataset_key', '_gtfs_dataset_name', 
        'trip_id',
        TIMESTAMP_COL,
        'x', 'y'
    ] + SEGMENT_IDENTIFIER_COLS
    
    rt_operators = helpers.import_vehicle_positions(
        SEGMENT_GCS,
        f"{VP_FILE}_{analysis_date}/",
        file_type = "df",
        columns = ["gtfs_dataset_key"],
        partitioned=True
    ).gtfs_dataset_key.unique().compute().tolist()
    
    operator_vps = [
        delayed(helpers.import_vehicle_positions)(
            SEGMENT_GCS,
            f"{VP_FILE}_{analysis_date}/",
            file_type = "df",
            columns = vp_keep_cols,
            filters = [("gtfs_dataset_key", "==", rt_key)],
            partitioned = True
        ) for rt_key in rt_operators
    ]
        
    operator_segments = [
        delayed(helpers.import_segments)(
            SEGMENT_GCS,
            f"{SEGMENT_FILE}_{analysis_date}", 
            filters = [("gtfs_dataset_key", "==", rt_key)],
            columns = SEGMENT_IDENTIFIER_COLS + ["geometry"]
        ) for rt_key in rt_operators
    ]

    vp_linear_ref_dfs = [
        delayed(wrangle_shapes.linear_reference_vp_against_segment)( 
            vp, 
            segments, 
            SEGMENT_IDENTIFIER_COLS
        ).persist() 
        for vp, segments in zip(operator_vps, operator_segments)
    ]
          
    time1 = datetime.datetime.now()
    logger.info(f"linear referencing: {time1 - time0}")

    
    results = [
        delayed(segment_calcs.calculate_speed_by_segment_trip)(
            operator_linear_ref, 
            SEGMENT_IDENTIFIER_COLS,
            TIMESTAMP_COL
        ) for operator_linear_ref in vp_linear_ref_dfs
    ]
    
    time2 = datetime.datetime.now()
    logger.info(f"calculate speeds: {time2 - time1}")
    
    dask_utils.compute_and_export(
        results, 
        gcs_folder = SEGMENT_GCS, 
        file_name = f"{EXPORT_FILE}_{analysis_date}",
        export_single_parquet = False
    )
    

if __name__ == "__main__": 
    #from dask.distributed import Client
    
    #client = Client("dask-scheduler.dask.svc.cluster.local:8786")
    LOG_FILE = "../logs/speeds_by_segment_trip.log"
    logger.add(LOG_FILE, retention="3 months")
    logger.add(sys.stderr, 
               format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}", 
               level="INFO")
    
    logger.info(f"Analysis date: {analysis_date}")
    
    start = datetime.datetime.now()

    STOP_SEG_DICT = helpers.get_parameters(CONFIG_PATH, "stop_segments")
    
    linear_referencing_and_speed_by_segment(
        analysis_date, 
        dict_inputs = STOP_SEG_DICT
    )
    
    logger.info(f"speeds for stop segments: {datetime.datetime.now() - start}")
    logger.info(f"execution time: {datetime.datetime.now() - start}")
    
    #client.close()
        