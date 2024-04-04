"""
Concatenate downloaded monthly scheduled service 
table across years.

Attach organization_source_record_id and 
schedule_gtfs_dataset_key.
"""
import pandas as pd
from segment_speed_utils import helpers, time_helpers, time_series_utils
from shared_utils import rt_dates
from update_vars import GTFS_DATA_DICT, SCHED_GCS

if __name__ == "__main__":
    
    MONTHLY_SERVICE = GTFS_DATA_DICT.schedule_tables.monthly_scheduled_service
    CROSSWALK = GTFS_DATA_DICT.schedule_tables.gtfs_key_crosswalk
    
    year_list = [2023, 2024]
    analysis_date_list = (rt_dates.y2024_dates + 
                          rt_dates.y2023_dates + 
                          rt_dates.oct_week + 
                          rt_dates.apr_week)
    
    df = pd.concat(
        [pd.read_parquet(
            f"{SCHED_GCS}{MONTHLY_SERVICE}_{y}.parquet") 
         for y in year_list], 
        axis=0, ignore_index=True
    ).rename(columns = {
        "source_record_id": "schedule_source_record_id"
    })

    df = df.assign(
        day_name = df.day_type.map(time_helpers.DAY_TYPE_DICT)
    )
    
    # Compile all the dates we have crosswalks
    # drop duplicates and we should capture all the schedule_source_record_ids
    # we need and attach schedule_gtfs_dataset_key and organization info
    # use this to filter in the digest
    crosswalk = time_series_utils.concatenate_datasets_across_dates(
        SCHED_GCS,
        CROSSWALK,
        analysis_date_list,
        data_type = "df",
        columns = [
            "schedule_source_record_id", 
            "schedule_gtfs_dataset_key",
            "organization_source_record_id", "organization_name", 
        ],
    ).drop(
        columns = "service_date"
    ).drop_duplicates().reset_index(drop=True)

    df2 = pd.merge(
        df,
        crosswalk,
        on = "schedule_source_record_id",
        how = "inner",
    )
    
    df2.to_parquet(
        f"{SCHED_GCS}{MONTHLY_SERVICE}.parquet"
    ) 