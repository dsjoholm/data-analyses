import geopandas as gpd
import pandas as pd

from calitp_data_analysis import utils
from segment_speed_utils import gtfs_schedule_wrangling, time_series_utils
from segment_speed_utils.project_vars import SEGMENT_GCS, RT_SCHED_GCS, SCHED_GCS

route_time_cols = ["schedule_gtfs_dataset_key", 
                   "route_id", "direction_id", "time_period"]

sort_cols = route_time_cols + ["service_date"]

def concatenate_schedule_by_route_direction(
    date_list: list
) -> pd.DataFrame:
    """
    Concatenate schedule data that's been 
    aggregated to route-direction-time_period.
    """
    df = time_series_utils.concatenate_datasets_across_months(
        RT_SCHED_GCS,
        "schedule_route_dir/schedule_route_direction_metrics",
        date_list,
        data_type = "df",
        columns = route_time_cols + [
            "avg_sched_service_min", 
            "avg_stop_meters",
            "n_trips", "frequency",]
    ).sort_values(sort_cols).reset_index(drop=True).rename(
        columns = {"n_trips": "n_scheduled_trips"}
    )    
    
    return df


def concatenate_segment_speeds_by_route_direction(
    date_list: list
) -> gpd.GeoDataFrame:
    """
    Concatenate segment speeds data that's been 
    aggregated to route-direction-time_period.
    """
    df = time_series_utils.concatenate_datasets_across_months(
        SEGMENT_GCS,
        "rollup_singleday/speeds_route_dir_segments",
        date_list,
        data_type = "gdf",
        columns = route_time_cols + [
            "stop_pair", "p20_mph", "p50_mph", 
            "p80_mph", "geometry"]
    ).sort_values(sort_cols).reset_index(drop=True)
    
    return df


def concatenate_speeds_by_route_direction(
    date_list: list
) -> pd.DataFrame: 
    """
    Concatenate rt vs schedule data that's been 
    aggregated to route-direction-time_period.
    """
    df = time_series_utils.concatenate_datasets_across_months(
        SEGMENT_GCS,
        "rollup_singleday/speeds_route_dir",
        date_list,
        data_type = "df",
        columns = route_time_cols + ["speed_mph"]
    ).sort_values(sort_cols).reset_index(drop=True)
    
    return df


def concatenate_rt_vs_schedule_by_route_direction(
    date_list: list
) -> pd.DataFrame:
    
    df = time_series_utils.concatenate_datasets_across_months(
        RT_SCHED_GCS,
        "vp_route_dir/route_direction_metrics",
        date_list,
        data_type = "df",
    ).sort_values(sort_cols).reset_index(drop=True).rename(
        columns = {"n_trips": "vp_trips"}
    )
    
    # We'll add this back in after merging
    # because these would be NaN if it's not in schedule
    drop_cols = [
        "base64_url", "organization_source_record_id",
        "organization_name", "caltrans_district"
    ]
    
    df = df.drop(columns = drop_cols)
    
    return df

def merge_in_standardized_route_names(
    df: pd.DataFrame, 
) -> pd.DataFrame:
    standardized_route_names = pd.read_parquet(
        f"{SCHED_GCS}standardized_route_ids.parquet",
        columns = ["schedule_gtfs_dataset_key", "name", 
                   "route_id", "service_date",
                   "recent_route_id2", "recent_combined_name"],
    )
    
    if "name" in df.columns:
        df = df.drop(columns = "name")
    
    df = pd.merge(
        df,
        standardized_route_names,
        on = ["schedule_gtfs_dataset_key", 
              "route_id", "service_date"],
        how = "left",
    )
    
    df = df.assign(
        recent_combined_name = df.recent_combined_name.str.replace("__", " ")
    ).drop(
        columns = ["route_id"]
    ).rename(
        columns = {
            "recent_route_id2": "route_id",
            "recent_combined_name": "route_combined_name"
        }
    )

    return df


if __name__ == "__main__":
    
    from shared_utils.rt_dates import y2023_dates, y2024_dates
    
    analysis_date_list = y2024_dates + y2023_dates 
    
    df_sched = concatenate_schedule_by_route_direction(analysis_date_list)
    
    df_avg_speeds = concatenate_speeds_by_route_direction(analysis_date_list)
                    
    df_rt_sched = (concatenate_rt_vs_schedule_by_route_direction(analysis_date_list)
                   .astype({"direction_id": "float"})
                  )
    
    df = pd.merge(
        df_sched,
        df_rt_sched,
        on = route_time_cols + ["service_date"],
        how = "outer",
        indicator = "sched_rt_category"
    ).merge(
        df_avg_speeds,
        on = route_time_cols + ["service_date"],
        how = "outer",
    )
    
    df= df.assign(
        sched_rt_category = df.sched_rt_category.map(
            gtfs_schedule_wrangling.sched_rt_category_dict)
    ).pipe(
        merge_in_standardized_route_names
    )

    df.to_parquet(
        f"{RT_SCHED_GCS}digest/schedule_vp_metrics.parquet"
    )
    
    segment_speeds = concatenate_segment_speeds_by_route_direction(
        analysis_date_list
    ).pipe(
        merge_in_standardized_route_names
    ).astype({"direction_id": "int64"}) #Int64 doesn't work for gdf
    
    utils.geoparquet_gcs_export(
        segment_speeds,
        RT_SCHED_GCS,
        f"digest/segment_speeds"
    )