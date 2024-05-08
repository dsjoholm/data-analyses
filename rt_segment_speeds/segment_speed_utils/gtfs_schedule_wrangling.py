"""
All kinds of GTFS schedule table wrangling.
"""
import geopandas as gpd
import pandas as pd
import dask.dataframe as dd

from typing import Literal, Union

from segment_speed_utils import helpers, time_helpers
from shared_utils import portfolio_utils, rt_utils
from segment_speed_utils.project_vars import SEGMENT_GCS 

sched_rt_category_dict = {
    "left_only": "schedule_only",
    "both": "schedule_and_vp",
    "right_only": "vp_only"
}

CA_AMTRAK = ["Pacific Surfliner", "San Joaquins", 
             "Coast Starlight", "Capitol Corridor"]


def amtrak_trips(
    analysis_date: str,
    inside_ca: bool = True
) -> pd.DataFrame:
    """
    Return Amtrak table, either for routes primarily inside CA or outside CA.
    """
    
    if inside_ca:
        filters = [[("name", "==", "Amtrak Schedule"), 
                    ("route_long_name", "in", CA_AMTRAK)]]
    else:
        filters = [[("name", "==", "Amtrak Schedule"), 
                    ("route_long_name", "not in", CA_AMTRAK)]]
    
    trips = helpers.import_scheduled_trips(
        analysis_date,
        get_pandas = True,
        filters = filters,
        columns = None
    )
       
    return trips
    

def exclude_scheduled_operators(
    trips: pd.DataFrame, 
    analysis_date: str,
    exclude_me: list = ["*Flex"],
    include_amtrak_routes: list = CA_AMTRAK
) -> pd.DataFrame:
    """
    Exclude certain operators by name.
    Here, we always want to exclude Amtrak Schedule because
    it runs outside of CA.
    """
    substrings_to_exclude = [i for i in exclude_me if "*" in i]
    
    if len(substrings_to_exclude) > 0:
        substrings = [i.replace("*", "") for i in substrings_to_exclude]
        for i in substrings:
            trips = trips[~trips.name.str.contains(i)].reset_index(drop=True)
    
    trips = trips[~trips.name.isin(exclude_me)].reset_index(drop=True)
    
    outside_ca_amtrak = helpers.import_scheduled_trips(
        analysis_date,
        columns = ["trip_instance_key"],
        filters = [[("name", "==", "Amtrak Schedule"), 
                   ("route_long_name", "not in", include_amtrak_routes)]],
    ).trip_instance_key.unique()
    
    trips = trips[
        ~trips.trip_instance_key.isin(outside_ca_amtrak)
    ].reset_index(drop=True)
    
    return trips


def stop_arrivals_per_stop(
    stop_times: pd.DataFrame,
    group_cols: list,
    count_col: str = "trip_id"
) -> pd.DataFrame:
    """
    Aggregate stop_times by list of grouping columns 
    and count number of stop arrivals.
    """
    arrivals_by_stop = (stop_times
                        .groupby(group_cols, 
                                 observed=True, group_keys=False)
                        .agg({count_col: 'count'})
                        .reset_index()
                        .rename(columns = {count_col: "n_arrivals"})          
                     )    
    return arrivals_by_stop
    
    
def add_peak_offpeak_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a single peak_offpeak column based on the time-of-day column.
    """
    df = df.assign(
        peak_offpeak = df.time_of_day.map(time_helpers.TIME_OF_DAY_DICT)
    )
    
    return df

def add_weekday_weekend_column(df: pd.DataFrame) -> pd.DataFrame:
    df = df.assign(
        weekday_weekend = df.service_date.dt.day_name().map(time_helpers.WEEKDAY_DICT)
    )
    
    return df
    
    
def aggregate_time_of_day_to_peak_offpeak(
    df: pd.DataFrame,
    group_cols: list,
    long_or_wide: Literal["long", "wide"] = "wide"
) -> pd.DataFrame:
    """
    Aggregate time-of-day bins into peak/offpeak periods.
    Return n_trips and frequency for grouping of columns (route-direction, etc).
    Allow wide or long df to be returned.
    """    
    peak_hours = sum(v for k, v in time_helpers.HOURS_BY_TIME_OF_DAY.items() 
                 if k in time_helpers.PEAK_PERIODS) 
    
    offpeak_hours = sum(v for k, v in time_helpers.HOURS_BY_TIME_OF_DAY.items() 
                 if k not in time_helpers.PEAK_PERIODS) 
    
    df = add_peak_offpeak_column(df)
    
    all_day = (df.groupby(group_cols)
               .agg({"trip_instance_key": "count"})
               .reset_index()
               .assign(time_period = "all_day")
              )
    
    peak_offpeak = (df.groupby(group_cols + ["peak_offpeak"])
                    .agg({"trip_instance_key": "count"})
                    .reset_index()
                    .rename(columns = {"peak_offpeak": "time_period"})
                   )
    
    df2 = pd.concat(
        [all_day, peak_offpeak], 
        axis=0, ignore_index = True
    ).rename(columns = {"trip_instance_key": "n_trips"})

    
    # Add service frequency (trips per hour)
    # there are different number of hours in peak and offpeak periods
    df2 = df2.assign(
        frequency = df2.apply(
            lambda x:
            round(x.n_trips / peak_hours, 2) if x.time_period=="peak"
            else round(x.n_trips / offpeak_hours, 2) if x.time_period=="offpeak"
            else round(x.n_trips / (peak_hours + offpeak_hours), 2), axis=1
        )
    )
    
    if long_or_wide == "long":
        return df2
    
    elif long_or_wide == "wide":
        # Reshape from wide to long
        # get rid of multiindex column names
        df3 = df2.pivot(index=group_cols, 
              columns="time_period",
              values=["n_trips", "frequency"]
             )

        df3.columns = [f'{b}_{a}' for a, b in df3.columns]
        df3 = df3.reset_index()

        return df3

    
def get_vp_trip_time_buckets(analysis_date: str) -> pd.DataFrame:
    """
    Assign trips to time-of-day.
    """
    df = dd.read_parquet(
        f"{SEGMENT_GCS}vp_usable_{analysis_date}",
        columns=[
            "trip_instance_key",
            "location_timestamp_local",
        ],
    )

    df2 = (
        df.groupby(["trip_instance_key"])
        .agg({"location_timestamp_local": "min"})
        .reset_index()
        .rename(columns={"location_timestamp_local": "min_time"})
    ).compute()

    df2 = df2.assign(
        time_of_day=df2.apply(
            lambda x: rt_utils.categorize_time_of_day(x.min_time), axis=1
        )
    )[["time_of_day","trip_instance_key"]]
    
    return df2


def get_trip_time_buckets(analysis_date: str) -> pd.DataFrame:
    """
    Assign trips to time-of-day.
    """
    keep_trip_cols = [
        "trip_instance_key", 
        "service_hours", 
        "trip_first_departure_datetime_pacific"
    ]
    
    trips = helpers.import_scheduled_trips(
        analysis_date,
        columns = keep_trip_cols,
        get_pandas = True
    )
                              
    trips = trips.assign(
        time_of_day = trips.apply(
            lambda x: rt_utils.categorize_time_of_day(
                x.trip_first_departure_datetime_pacific), axis=1), 
        scheduled_service_minutes = trips.service_hours * 60
    )
    
    return trips


def attach_scheduled_route_info(
    analysis_date: str
) -> pd.DataFrame:
    """
    Add route id, direction id,
    off_peak, and time_of_day columns. Do some
    light cleaning.
    """
    route_info = helpers.import_scheduled_trips(
        analysis_date,
        columns=[
            "gtfs_dataset_key", "trip_instance_key",
            "route_id", "direction_id",
        ],
        get_pandas=True,
    )
    
    sched_time_of_day = (
        get_trip_time_buckets(analysis_date)          
        [["trip_instance_key", "time_of_day", "scheduled_service_minutes"]]
        .rename(columns={"time_of_day": "sched_time_of_day"})
    )
    
    rt_time_of_day = (
        get_vp_trip_time_buckets(analysis_date)
        .rename(columns={"time_of_day": "rt_time_of_day"})
    )

    time_df = pd.merge(
        route_info,
        sched_time_of_day,
        on = "trip_instance_key",
        how = "inner"
    )
    
    time_df = time_df.merge(
        rt_time_of_day,
        on = "trip_instance_key",
        how = "outer",
        indicator="sched_rt_category"
    )
    
    time_df = time_df.assign(
        route_id = time_df.route_id.fillna("Unknown"),
        time_of_day = time_df.sched_time_of_day.fillna(
            time_df.rt_time_of_day),
        sched_rt_category = time_df.sched_rt_category.map(
            sched_rt_category_dict),
    ).drop(
        columns = ['sched_time_of_day', 'rt_time_of_day']
    )
    
    return time_df

def most_recent_route_info(
    df: pd.DataFrame,
    group_cols: list,
    route_col: str
) -> pd.DataFrame:
    """
    Find the most recent value across a grouping.
    Ex: if we group by route_id, we can find the most recent 
    value for route_long_name.
    
    Needs a date column to work.
    """
    sort_order = [True for c in group_cols]
    
    most_recent = (df.sort_values(group_cols + ["service_date"], 
                                  ascending = sort_order + [False])
                   .drop_duplicates(subset = group_cols)  
                   .rename(columns = {route_col: f"recent_{route_col}"})
                  )
    
    df2 = pd.merge(
        df,
        most_recent[group_cols + [f"recent_{route_col}"]],
        on = group_cols,
        how = "left"
    )
    
    return df2


OPERATORS_USE_HYPHENS = [
    "Monterey Salinas", "LA Metro",
    "BART", # Beige - N, Beige - S
    "MVGO", # B - AM, B - PM
]

OPERATORS_USE_UNDERSCORES = [
    "Roseville", # 5_AM, 5_PM
]

def standardize_route_id(
    row, 
    gtfs_name_col: str, 
    route_col: str
) -> str:
    """
    Standardize route_id across time. 
    For certain operators, we can parse away the suffix after an
    hyphen or underscore.
    Must include a column that corresponds to `gtfs_dataset_name`.
    """
    word = row[route_col]
    
    if any(word in row[gtfs_name_col] for word in OPERATORS_USE_HYPHENS): 
        word = word.split("-")[0]
    
    if any(word in row[gtfs_name_col] for word in OPERATORS_USE_UNDERSCORES):
        word = word.split("_")[0]
    
    
    word = word.strip()
    
    return word


def most_common_shape_by_route_direction(analysis_date: str) -> gpd.GeoDataFrame:
    """
    Find shape_id with most trips for that route-direction.
    Merge in shape geometry.
    """
    route_dir_cols = ["gtfs_dataset_key", "route_id", "direction_id"]
    
    keep_trip_cols = route_dir_cols + [
        "trip_instance_key", "shape_id", "shape_array_key"
    ]
    
    trips = helpers.import_scheduled_trips(
        analysis_date, 
        columns = keep_trip_cols,
        get_pandas = True
    ).rename(columns = {"schedule_gtfs_dataset_key": "gtfs_dataset_key"})                 
    sorting_order = [True for i in route_dir_cols]
    
    most_common_shape = (
        trips.groupby(route_dir_cols + ["shape_id", "shape_array_key"], 
                      observed=True, group_keys = False)
        .agg({"trip_instance_key": "count"})
        .reset_index()
        .sort_values(route_dir_cols + ["trip_instance_key"], 
                     ascending = sorting_order + [False])
        .drop_duplicates(subset=route_dir_cols)
        .reset_index(drop=True)
        [route_dir_cols + ["shape_id", "shape_array_key"]]
    ).rename(columns = {
        "gtfs_dataset_key": "schedule_gtfs_dataset_key", 
        "shape_id": "common_shape_id"
    })  
    
    shape_geom = helpers.import_scheduled_shapes(
        analysis_date,
        columns = ["shape_array_key", "geometry"],
    )
    
    common_shape_geom = pd.merge(
        shape_geom,
        most_common_shape,
        on = "shape_array_key",
        how = "inner"
    ).drop(columns = "shape_array_key")
    
    route_info = helpers.import_scheduled_trips(
        analysis_date,
        columns = ["gtfs_dataset_key", "route_id", 
                   "route_long_name", "route_short_name", "route_desc"]
    ).drop_duplicates().pipe(
        portfolio_utils.add_route_name
    ).drop(columns = ["route_long_name", "route_short_name", "route_desc"])
    
    del shape_geom, most_common_shape
    
    common_shape_geom2 = pd.merge(
        common_shape_geom,
        route_info.rename(columns = {"route_name_used": "route_name"}),
        on = ["schedule_gtfs_dataset_key", "route_id"]
    )
    
    return common_shape_geom2
 
    
def longest_shape_by_route_direction(
    analysis_date: str
) -> gpd.GeoDataFrame:
    """
    For every route-direction, keep the row with 
    longest length (meters) for shape_array_key.
    """
    routes = helpers.import_scheduled_trips(
        analysis_date,
        columns = ["feed_key", "gtfs_dataset_key", 
                   "route_id", "direction_id", "route_key",
                   "shape_array_key"],
        get_pandas = True
    )
    
    routes2 = helpers.import_scheduled_shapes(
        analysis_date,
        columns = ["shape_array_key", "geometry"],
        get_pandas = True
    ).merge(
        routes,
        on = "shape_array_key",
        how = "inner"
    )
    
    sort_cols = ["feed_key", "route_id", "direction_id"]
    
    routes2 = routes2.assign(
        route_length = routes2.geometry.length
    ).sort_values(
        sort_cols + ["route_length"],
        ascending = [True for i in sort_cols] + [False]
    ).drop_duplicates(subset=sort_cols).reset_index(drop=True)
    
    return routes2

    
def gtfs_segments_rename_cols(
    df: pd.DataFrame, 
    natural_identifier: bool = True
) -> pd.DataFrame:
    """
    To use gtfs_segments package, we need to always have
    natural identifiers for GTFS.
    But, since that package relies on each feed being
    processed individually, we need to use our internal 
    keys to make sure we're not mixing up operators.
    """
    if natural_identifier:
        df = df.rename(columns = {
            "trip_instance_key": "trip_id",
            "shape_array_key": "shape_id"
        })
    else:
        df = df.rename(columns = {
            "trip_id": "trip_instance_key",
            "shape_id": "shape_array_key"
        })
    return df


def merge_operator_identifiers(
    df: pd.DataFrame, 
    analysis_date_list: list
) -> pd.DataFrame:
    """
    Carrying a lot of these operator identifiers is not 
    inconsequential, esp when we need to run a week's segment speeds
    in one go.
    Instead, we'll just merge it back on before we export.
    """
    crosswalk = pd.concat([
        helpers.import_schedule_gtfs_key_organization_crosswalk(
            analysis_date,
        ).drop(columns = ["itp_id", "schedule_source_record_id"]) 
        for analysis_date in analysis_date_list],
        axis=0, ignore_index=True
    ).drop_duplicates()
    
    df = pd.merge(
        df,
        crosswalk,
        on = "schedule_gtfs_dataset_key",
        how = "inner"
    )
    
    return df