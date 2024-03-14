"""
"""
import datetime
import pandas as pd
import sys

from loguru import logger

from segment_speed_utils import (gtfs_schedule_wrangling, 
                                 metrics
                                )
from segment_speed_utils.project_vars import RT_SCHED_GCS
from segment_speed_utils.time_series_utils import ROUTE_DIR_COLS

def route_metrics(
    analysis_date: str, 
    dict_inputs: dict
) -> pd.DataFrame:
  
    start = datetime.datetime.now()
    
    TRIP_EXPORT = dict_inputs["trip_metrics"]
    ROUTE_EXPORT = dict_inputs["route_direction_metrics"]

    trip_df = pd.read_parquet(
        f"{RT_SCHED_GCS}{TRIP_EXPORT}_{analysis_date}.parquet"
    )
    
    route_df = metrics.concatenate_peak_offpeak_allday_averages(
        trip_df,
        group_cols = ["schedule_gtfs_dataset_key"] + ROUTE_DIR_COLS,
        metric_type = "rt_vs_schedule"
    ).pipe(
        metrics.derive_rt_vs_schedule_metrics
    ).pipe(
        gtfs_schedule_wrangling.merge_operator_identifiers,
        [analysis_date]
    )
    
    # Save
    route_df.to_parquet(
        f"{RT_SCHED_GCS}{ROUTE_EXPORT}_{analysis_date}.parquet"
    )
    
    end = datetime.datetime.now()
    logger.info(f"route aggregation {analysis_date}: {end - start}")
    
    return 

if __name__ == "__main__":
    
    LOG_FILE = "../logs/rt_v_scheduled_route_metrics.log"
    logger.add(LOG_FILE, retention="3 months")
    logger.add(sys.stderr, 
               format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}", 
               level="INFO")
    
    from update_vars import analysis_date_list, CONFIG_DICT
    
    for analysis_date in analysis_date_list: 
        route_metrics(analysis_date, CONFIG_DICT)
