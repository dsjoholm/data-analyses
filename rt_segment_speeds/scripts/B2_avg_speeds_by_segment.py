"""
Quick aggregation for speed metrics by segment
"""
import datetime
import geopandas as gpd
import pandas as pd
import sys

from loguru import logger

from segment_speed_utils import helpers, sched_rt_utils
from segment_speed_utils.project_vars import (SEGMENT_GCS, analysis_date, 
                                              CONFIG_PATH)
from shared_utils import utils, geography_utils


def calculate_avg_speeds(
    df: pd.DataFrame,
    group_cols: list
) -> pd.DataFrame:
    """
    Calculate the median, 20th, and 80th percentile speeds 
    by groups.
    """
    # Take the average after dropping unusually high speeds
    grouped_df = df.groupby(group_cols, observed=True, group_keys=False)
    
    
    avg = (grouped_df
          .agg({
            "speed_mph": "median",
            "trip_id": "nunique"})
          .reset_index()
    )
    
    p20 = (grouped_df
           .agg({"speed_mph": lambda x: x.quantile(0.2)})
           .reset_index()  
          )
    
    p80 = (grouped_df
           .agg({"speed_mph": lambda x: x.quantile(0.8)})
           .reset_index()  
          )
    
    stats = pd.merge(
        avg.rename(columns = {"speed_mph": "p50_mph", 
                              "trip_id": "n_trips"}),
        p20.rename(columns = {"speed_mph": "p20_mph"}),
        on = group_cols,
        how = "left"
    ).merge(
        p80.rename(columns = {"speed_mph": "p80_mph"}),
        on = group_cols,
        how = "left"
    )
    
    # Clean up for map
    speed_cols = [c for c in stats.columns if "_mph" in c]
    stats[speed_cols] = stats[speed_cols].round(2)
    
    return stats
    
    
def speeds_with_segment_geom(
    analysis_date: str, 
    max_speed_cutoff: int = 70,
    dict_inputs: dict = {}
) -> gpd.GeoDataFrame: 
    """
    Import the segment-trip table. 
    Average the speed_mph across all trips present in the segment.
    """
    SEGMENT_FILE = dict_inputs["segments_file"]
    SEGMENT_IDENTIFIER_COLS = dict_inputs["segment_identifier_cols"]
    SPEEDS_FILE = dict_inputs["stage4"]
    
    df = pd.read_parquet(
        f"{SEGMENT_GCS}{SPEEDS_FILE}_{analysis_date}", 
        filters = [[("speed_mph", "<=", max_speed_cutoff), 
                    ("sec_elapsed", ">", 0), 
                    ("meters_elapsed", ">", 0)
                   ]]
    )
    
    df = df[df.speed_mph.notna() ].reset_index(drop=True)
    
    time_of_day_df = sched_rt_utils.get_trip_time_buckets(analysis_date)
    
    df2 = pd.merge(
        df, 
        time_of_day_df, 
        on = ["gtfs_dataset_key", "trip_id"], 
        how = "inner"
    )
    
    all_day = calculate_avg_speeds(
        df2, 
        SEGMENT_IDENTIFIER_COLS
    )
    
    peak = calculate_avg_speeds(
        df2[df2.time_of_day.isin(["AM Peak", "PM Peak"])], 
        SEGMENT_IDENTIFIER_COLS
    )
    
    stats = pd.concat([
        all_day.assign(time_of_day = "all_day"),
        peak.assign(time_of_day = "peak")
    ], axis=0)
    
    
    # Merge in segment geometry
    segments = helpers.import_segments(
        SEGMENT_GCS,
        f"{SEGMENT_FILE}_{analysis_date}",
        columns = SEGMENT_IDENTIFIER_COLS + [
            "gtfs_dataset_key", 
            "stop_id",
            "loop_or_inlining",
            "geometry", 
            "district", "district_name"
        ]
    ).to_crs(geography_utils.WGS84)
    
    gdf = pd.merge(
        segments,
        stats,
        on = SEGMENT_IDENTIFIER_COLS,
        how = "inner"
    )
    
    return gdf


if __name__ == "__main__":
    
    LOG_FILE = "../logs/avg_speeds.log"
    logger.add(LOG_FILE, retention="3 months")
    logger.add(sys.stderr, 
               format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}", 
               level="INFO")
    
    logger.info(f"Analysis date: {analysis_date}")
    
    start = datetime.datetime.now()
    STOP_SEG_DICT = helpers.get_parameters(CONFIG_PATH, "stop_segments")
    EXPORT_FILE = f'{STOP_SEG_DICT["stage5"]}_{analysis_date}'
    
    MAX_SPEED = 70
    
    # Average the speeds for segment for entire day
    # Drop speeds above our max cutoff
    stop_segment_speeds = speeds_with_segment_geom(
        analysis_date, 
        max_speed_cutoff = MAX_SPEED,
        dict_inputs = STOP_SEG_DICT
    )
        
    utils.geoparquet_gcs_export(
        stop_segment_speeds,
        SEGMENT_GCS,
        EXPORT_FILE
    )
    
    logger.info(f"execution time: {datetime.datetime.now() - start}")