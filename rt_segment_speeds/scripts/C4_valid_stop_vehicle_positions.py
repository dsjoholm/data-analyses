"""
Filter out unusable trips.
Keep the enter / exit points for each stop segment.
"""
import dask.dataframe as dd
import dask_geopandas as dg
import datetime
import geopandas as gpd
import pandas as pd
import sys
import warnings

from dask import delayed
from loguru import logger
from shapely.errors import ShapelyDeprecationWarning
warnings.filterwarnings("ignore", category=ShapelyDeprecationWarning)

from shared_utils import dask_utils
from segment_speed_utils import helpers, segment_calcs
from segment_speed_utils.project_vars import SEGMENT_GCS, analysis_date

if __name__ == "__main__": 
    #from dask.distributed import Client
    
    #client = Client("dask-scheduler.dask.svc.cluster.local:8786")
    
    logger.add("../logs/C4_valid_stop_vehicle_positions.log", 
               retention="3 months")
    logger.add(sys.stderr, 
               format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}", 
               level="INFO")
    
    logger.info(f"Analysis date: {analysis_date}")
    
    start = datetime.datetime.now()
    
    INPUT_FILE_PREFIX = "vp_stop_segment"
    RT_OPERATORS = helpers.operators_with_data(
        gcs_folder = f"{SEGMENT_GCS}vp_sjoin/",
        file_name_prefix = f"{INPUT_FILE_PREFIX}_",
        analysis_date = analysis_date
    )  
    
    results = []
    
    for rt_dataset_key in RT_OPERATORS:
        logger.info(f"start {rt_dataset_key}")
        
        start_id = datetime.datetime.now()

        # https://docs.dask.org/en/stable/delayed-collections.html
        operator_vp_segments = delayed(
            helpers.import_vehicle_positions)(
            f"{SEGMENT_GCS}vp_sjoin/",
            f"{INPUT_FILE_PREFIX}_{rt_dataset_key}_{analysis_date}",
            file_type = "df",
        )
        
        operator_vp_segments = operator_vp_segments.repartition(
            partition_size = "85MB")
        
        time1 = datetime.datetime.now()
        logger.info(f"imported data: {time1 - start_id}")
        
        # filter to usable trips
        # pass valid_operator_vp down 
        # valid_operator_vp = delayed(helpers.exclude_unusable_trips)(
        # operator_vp_segments, trips_list)
        #logger.info(f"filter out to only valid trips: {}")
        
        vp_pared = delayed(segment_calcs.keep_min_max_timestamps_by_segment)(
            operator_vp_segments, 
            segment_cols = ["shape_array_key", "stop_sequence"],
            timestamp_col = "location_timestamp"
        )
        
        results.append(vp_pared)
        
        time2 = datetime.datetime.now()
        logger.info(f"keep enter/exit points by segment-trip: {time2 - time1}")
        
        end_id = datetime.datetime.now()
        logger.info(f"gtfs_dataset_key: {rt_dataset_key}: {end_id-start_id}")

    
    time3 = datetime.datetime.now()
    logger.info(f"start compute and export of results")
    
    # Unpack delayed results
    dask_utils.compute_and_export(
        results, 
        gcs_folder = f"{SEGMENT_GCS}",
        file_name = f"vp_pared_stops_{analysis_date}",
        export_single_parquet=False
    )
    
    time4 = datetime.datetime.now()
    logger.info(f"exported all vp pared: {time4 - time3}")

    end = datetime.datetime.now()
    logger.info(f"execution time: {end-start}")
    
    #client.close()
        