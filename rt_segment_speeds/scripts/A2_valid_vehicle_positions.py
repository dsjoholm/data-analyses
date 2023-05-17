"""
Filter out unusable trips using RT trip diagnostics.

Keep the enter / exit points for each segment.
"""
import dask.dataframe as dd
import datetime
import numpy as np
import pandas as pd
import sys

from dask import delayed, compute
from loguru import logger
from typing import Literal

from segment_speed_utils import helpers, segment_calcs
from segment_speed_utils.project_vars import (SEGMENT_GCS, analysis_date, 
                                              CONFIG_PATH)

"""
References

Why call compute twice on dask delayed?
https://stackoverflow.com/questions/56944723/why-sometimes-do-i-have-to-call-compute-twice-on-dask-delayed-functions

Parallelize dask aggregation
https://stackoverflow.com/questions/62352617/parallelizing-a-dask-aggregation

Dask delayed stuff
https://docs.dask.org/en/latest/delayed.htmls
https://tutorial.dask.org/03_dask.delayed.html
https://stackoverflow.com/questions/71736681/possible-overhead-on-dask-computation-over-list-of-delayed-objects
https://docs.dask.org/en/stable/delayed-collections.html
https://distributed.dask.org/en/latest/manage-computation.html
https://docs.dask.org/en/latest/delayed-best-practices.html

Map partitions has trouble computing result.
Just use partitioned df and don't use `ddf.map_partitions`.
"""     
def identify_stop_segment_cases(
    analysis_date: str, 
    grouping_col: str,
    loop_or_inlining: Literal[0, 1]
) -> np.ndarray:
    """
    Filter based on the column loop_or_inlining in the
    stops_projected file. 
    1 is special case, can have loops or inlining.
    0 is normal case
    """
    shape_cases = pd.read_parquet(
        f"{SEGMENT_GCS}stops_projected_{analysis_date}/",
        filters = [[("loop_or_inlining", "==", loop_or_inlining)]],
        columns = [grouping_col]
    )[grouping_col].unique().tolist()

    return shape_cases


def pare_down_vp_by_segment(
    analysis_date: str, 
    dict_inputs: dict = {}
):
    """
    Pare down vehicle positions that have been joined to segments
    to keep the enter / exit timestamps.
    Also, exclude any bad batches of trips.
    """
    time0 = datetime.datetime.now()
    
    USABLE_VP = dict_inputs["stage1"]
    INPUT_FILE_PREFIX = dict_inputs["stage2"]
    SEGMENT_IDENTIFIER_COLS = dict_inputs["segment_identifier_cols"]
    GROUPING_COL = dict_inputs["grouping_col"]
    TIMESTAMP_COL = dict_inputs["timestamp_col"]
    EXPORT_FILE = dict_inputs["stage3"]
    
    # Handle stop segments and the normal/special cases separately
    normal_shapes = identify_stop_segment_cases(
        analysis_date, GROUPING_COL, 0)
    
    # First, grab all the usable vp (with lat/lon columns)
    usable_vp = helpers.import_vehicle_positions(
        SEGMENT_GCS,
        f"{USABLE_VP}_{analysis_date}",
        file_type = "df",
        partitioned = True
    ).set_index("vp_idx")
        
    # Grab our results of vp_idx joined to segments
    seg_seq_col = [c for c in SEGMENT_IDENTIFIER_COLS 
                   if c != GROUPING_COL][0]
    
    vp_joined_to_segments_normal = dd.read_parquet(
        f"{SEGMENT_GCS}vp_sjoin/{INPUT_FILE_PREFIX}_{analysis_date}/",
        filters = [[(GROUPING_COL, "in", normal_shapes)]],
    ).set_index("vp_idx")
    
    # Merge these so that we have segment identifiers and lat/lon
    usable_normal_vp = dd.merge(
        usable_vp,
        vp_joined_to_segments_normal,
        left_index = True,
        right_index = True,
        how = "inner"
    )
    
    #usable_normal_vp.reset_index().to_parquet(
    #    f"{SEGMENT_GCS}{EXPORT_FILE}_temp",
    #    partition_on="gtfs_dataset_key"
    #)
    
    time1 = datetime.datetime.now()    
    logger.info(f"merge usable vp with sjoin results: {time1 - time0}")


    normal_vp_to_keep = segment_calcs.keep_min_max_timestamps_by_segment(
        usable_normal_vp,       
        segment_identifier_cols = SEGMENT_IDENTIFIER_COLS,
        timestamp_col = TIMESTAMP_COL
    )
        
    time2 = datetime.datetime.now()
    logger.info(f"keep enter/exit points: {time2 - time1}")

    normal_vp_to_keep.to_parquet(
        f"{SEGMENT_GCS}{EXPORT_FILE}_normal_{analysis_date}"
    )
    
    logger.info(f"exported: {datetime.datetime.now() - time2}")
    

    
if __name__ == "__main__":
    
    LOG_FILE = "../logs/valid_vehicle_positions.log"
    logger.add(LOG_FILE, retention="3 months")
    logger.add(sys.stderr, 
               format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}", 
               level="INFO")
    
    logger.info(f"Analysis date: {analysis_date}")
    
    start = datetime.datetime.now()
    
    STOP_SEG_DICT = helpers.get_parameters(CONFIG_PATH, "stop_segments")
   
    time1 = datetime.datetime.now()
    
    pare_down_vp_by_segment(
        analysis_date,
        dict_inputs = STOP_SEG_DICT
    )
    
    time2 = datetime.datetime.now()
    logger.info(f"pare down vp by stop segments {time2 - time1}")
    
    end = datetime.datetime.now()
    logger.info(f"execution time: {end-start}")