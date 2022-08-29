"""
Create dataset, at route-level.

Aggregate stop times df by time-of-day.
Add in competitive_route_variability df (created in E5_make_stripplot_data),
which is at the trip-level, and only keep the route-level stats.

Merge these so dataset has these route-level stats:
   num_stop_arrivals_*time_of_day
   num_trips_*time_of_day
   % and # trips competitive
   route_group, route_name
   
Output: bus_routes_aggregated_stats
"""
import dask.dataframe as dd
import intake
import geopandas as gpd
import pandas as pd

from calitp.sql import to_snakecase

from shared_utils import (geography_utils, gtfs_utils, 
                          rt_dates, rt_utils
                         )
from utils import GCS_FILE_PATH

ANALYSIS_DATE = rt_dates.DATES["may2022"]
catalog = intake.open_catalog("*.yml")
TRAFFIC_OPS_GCS = 'gs://calitp-analytics-data/data-analyses/traffic_ops/'


def subset_trips_and_stop_times(trips: dd.DataFrame, 
                                stop_times: dd.DataFrame,
                                itp_id_list: list, 
                                route_list: list) -> dd.DataFrame:
    """
    Subset trips with smaller list of ITP IDs and route_ids.
    Then subset stop times.
    
    Merge trips with stop times so stop_times also comes with route_ids.
    
    Add in time-of-day column.
    """
    subset_trips = trips[
        (trips.calitp_itp_id.isin(itp_id_list) & 
         (trips.route_id.isin(route_list)))
    ]

    keep_trip_keys = subset_trips.trip_key.unique().compute().tolist()
    
    # Get route_info
    with_route_id = subset_trips[
        ["calitp_itp_id", "trip_key", "route_id"]
    ].drop_duplicates()
    
    # Subset stop times, first keep only trip_keys found in trips
    # Trips give the routes we're interested in
    subset_stop_times = stop_times[stop_times.trip_key.isin(keep_trip_keys)]
    
    subset_stop_times2 = dd.merge(
        subset_stop_times,
        with_route_id,
        on = ["calitp_itp_id", "trip_key"],
        how = "inner"
    )
    
    stop_times_with_hr = gtfs_utils.fix_departure_time(subset_stop_times2)
    
    stop_times_binned = stop_times_with_hr.assign(
        time_of_day=stop_times_with_hr.apply(
            lambda x: rt_utils.categorize_time_of_day(x.departure_hour), axis=1, 
            meta=('time_of_day', 'str'))
    )
    
    return stop_times_binned


def aggregate_stat_by_time_of_day(df: dd.DataFrame, 
                                  group_cols: list, 
                                  stat_col: dict = {"trip_id": "nunique"}
                                 ) -> dd.DataFrame:
    """
    Aggregate given different group_cols.
    
    Avoid merging together, since dask df requires setting of metadata,
    and there isn't an easy way to pre-define what the metadata is in group_cols
    """    
    for key, value in stat_col.items():
        use_col = key
        agg = value
        
    # nunique seems to not work in groupby.agg
    # even though https://github.com/dask/dask/pull/8479 seems to resolve it?
    # alternative is to use nunique as series
    if agg=="nunique":
        agg_df = (df.groupby(group_cols)[use_col].nunique()
                    .reset_index()
                 )
    else:
        agg_df = (df.groupby(group_cols)
                .agg({use_col: agg})
                .reset_index()
                 )
        
    return agg_df
        

def aggregate_by_time_of_day(stop_times: dd.DataFrame, 
                             group_cols: list) -> pd.DataFrame:
    """
    Aggregate given different group_cols.
    Count each individual stop time (a measure of 'saturation' along a hwy corridor)
    or just count number of trips that occurred?
    """    
    # nunique seems to not work in groupby.agg
    # even though https://github.com/dask/dask/pull/8479 seems to resolve it?
    # alternative is to use nunique as series

    nunique_trips = aggregate_stat_by_time_of_day(
        stop_times, group_cols, stat_col = {"trip_id": "nunique"}
    ).rename(columns = {"trip_id": "trips"})
    
    count_stop_arrivals = aggregate_stat_by_time_of_day(
        stop_times, group_cols, stat_col = {"departure_hour": "count"}
    ).rename(columns = {"departure_hour": "stop_arrivals"})
    
    nunique_stops = aggregate_stat_by_time_of_day(
        stop_times, group_cols, stat_col = {"stop_id": "nunique"}
    ).rename(columns = {"stop_id": "stops"})
    
    # Merge aggregations
    ddf1 = dd.merge(
        nunique_trips,
        count_stop_arrivals,
        on = group_cols,
        how = "inner"
    )
    
    ddf2 = dd.merge(
        ddf1,
        count_stops,
        on = group_cols,
        how = "inner"
    ).compute()
            
    return ddf2


def reshape_long_to_wide(df: pd.DataFrame, 
                         group_cols: list,
                         long_col: str = 'time_of_day',
                         value_col: str = 'trips',
                         long_col_sort_order: list = ['owl', 'early_am', 
                                                      'am_peak', 'midday', 
                                                      'pm_peak', 'evening'],
                        )-> pd.DataFrame:
    """
    To reshape from long to wide, use df.pivot.
    Args in this function correspond this way:
    
    df.pivot(index=group_cols, columns = long_col, values = value_col)
    """
    # To reshape, cannot contain duplicate entries
    # Get it down to non-duplicate form
    # For stop-level, if you're reshaping on value_col==trip, that stop contains
    # the same trip info multiple times.
    df2 = df[group_cols + [long_col, value_col]].drop_duplicates()
    
    #https://stackoverflow.com/questions/22798934/pandas-long-to-wide-reshape-by-two-variables
    reshaped = df2.pivot(
        index=group_cols, columns=long_col,
        values=value_col
    ).reset_index().pipe(to_snakecase)

    # set the order instead of list comprehension, which will just do alphabetical
    add_prefix_cols = long_col_sort_order

    # Change the column order
    reshaped = reshaped.reindex(columns=group_cols + add_prefix_cols)

    # If there are NaNs, fill it with 0, then coerce to int
    reshaped[add_prefix_cols] = reshaped[add_prefix_cols].fillna(0).astype(int)

    # Add a total across time of day bins
    reshaped[f"{value_col}_total"] = reshaped[add_prefix_cols].sum(axis=1).astype(int)

    # Now, instead columns named am_peak, pm_peak, add a prefix 
    # to distinguish between num_trips and num_stop_arrivals
    reshaped.columns = [f"{value_col}_{c}" if c in add_prefix_cols else c
                            for c in reshaped.columns]

    return reshaped


def long_to_wide_format(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    """
    Take the long df, which is structured where each row is 
    a route_id-time_of_day combination, and columns are 
    'trips' and 'stop_arrivals' and 'stops'.
    
    Reshape it to being wide, so each row is route_id.
    """

    df = df.astype({"time_of_day": "category"})
    
    # Do the reshape to wide format separately
    # so the renaming of columns is cleaner
    time_of_day_sorted = ['owl', 'early_am', 'am_peak', 
                          'midday','pm_peak', 'evening']
    
    trips_reshaped = reshape_long_to_wide(
        df, group_cols = group_cols, 
        long_col = "time_of_day", 
        value_col="trips", long_col_sort_order = time_of_day_sorted)
    
    stop_arrivals_reshaped = reshape_long_to_wide(
        df, group_cols = group_cols, 
        long_col = "time_of_day", 
        value_col="stop_arrivals", long_col_sort_order = time_of_day_sorted)
    
    stops_reshaped = reshape_long_to_wide(
        df, group_cols = group_cols, 
        long_col = "time_of_day", 
        value_col="stops", long_col_sort_order = time_of_day_sorted)
    
    
    # Just keep subset of columns (don't need all time-of-day)?
    def only_peak_and_total(df: pd.DataFrame, 
                            group_cols: list, 
                            prefix: str = "trips"
                           ) -> pd.DataFrame:
        
        cols_to_sum = [f"{prefix}_am_peak", f"{prefix}_pm_peak"]
        df[f"{prefix}_peak"] = df[cols_to_sum].sum(axis=1)

        keep_cols = group_cols + [f"{prefix}_peak", f"{prefix}_total"]
        df2 = df[keep_cols]

        return df2
    
    trips_reshaped = only_peak_and_total(
        trips_reshaped, group_cols, prefix = "trips")
    stop_arrivals_reshaped = only_peak_and_total(
        stop_arrivals_reshaped, group_cols, prefix = "stop_arrivals")
    stops_reshaped = only_peak_and_total(
        stops_reshaped, group_cols, prefix = "stops")
    
    # After reshaping separately, merge it back together, and each row now is route-level
    df_wide = pd.merge(
        trips_reshaped, 
        stop_arrivals_reshaped,
        on = group_cols,
        how = "inner"
    ).merge(stops_reshaped,
            on = group_cols,
            how = "inner"
    )
        
    
    return df_wide


def get_competitive_routes() -> pd.DataFrame:
    """
    Trip-level data for whether the trip is competitive or not,
    with other columns that are route-level.
    
    Keep only the route-level columns.
    """
    trip_df = catalog.competitive_route_variability.read()
    
    route_level_cols = [
        "calitp_itp_id", "route_id", "route_group",
        "bus_difference_spread",
        "num_competitive", "pct_trips_competitive",
    ]

    route_df = geography_utils.aggregate_by_geography(
        trip_df,
        group_cols = route_level_cols,
        mean_cols = ["bus_multiplier", "bus_difference"],
        rename_cols = True
    )
    
    return route_df


if __name__=="__main__":
    # (1) Read in bus routes that run on highways to use for filtering in dask df
    bus_routes = catalog.bus_routes_on_hwys.read()
    
    keep_itp_ids = bus_routes.itp_id.unique().tolist()
    keep_routes = bus_routes.route_id.unique().tolist()
    
    '''
    gtfs_utils.all_trips_or_stoptimes_with_cached(
        dataset="st",
        analysis_date = ANALYSIS_DATE,
        itp_id_list = keep_itp_ids,
        export_path = GCS_FILE_PATH
    )
    
    # stops already cached for 5/4
    '''
    # (2) Combine stop_times and trips, and filter to routes that appear in bus_routes
    stop_times = dd.read_parquet(f"{GCS_FILE_PATH}st_{ANALYSIS_DATE}.parquet")
    trips = dd.read_parquet(f"{TRAFFIC_OPS_GCS}trips_{ANALYSIS_DATE}.parquet")
        
    # Subset stop times and merge with trips
    stop_times_with_hr = subset_trips_and_stop_times(
        trips, stop_times, 
        itp_id_list = keep_itp_ids, 
        route_list = keep_routes
    )
    
    # (3) Aggregate to route-level
    route_cols = ["calitp_itp_id", "service_date", "route_id"]
    
    # (3a) All stops on route
    by_route_and_time_of_day = aggregate_by_time_of_day(
        stop_times_with_hr, route_cols + ["time_of_day"]
    )
    
    by_route = long_to_wide_format(by_route_and_time_of_day, route_cols)
    
    by_route.to_parquet(f"{GCS_FILE_PATH}bus_routes_on_hwys_aggregated_stats.parquet")
    
    # (3b) Only stops on hwys for route
    stops_on_hwy = catalog.bus_stops_on_hwys.read()
    
    stop_times_with_hr_hwy = dd.merge(
        stop_times_with_hr,
        stops_on_hwy[["calitp_itp_id", "stop_id"]],
        on = ["calitp_itp_id", "stop_id"],
        how = "inner",
    )
    
    by_route_hwy_stops_and_time_of_day = aggregate_by_time_of_day(
        stop_times_with_hr_hwy, route_cols + ["time_of_day"]
    )
    
    by_route_hwy = long_to_wide_format(by_route_hwy_stops_and_time_of_day, route_cols)
    
    by_route_hwy.to_parquet(
        f"{GCS_FILE_PATH}bus_stops_on_hwys_aggregated_stats.parquet")
    
    
    # Merge in the competitive trip variability dataset
    # This contains, at the route-level, % trips competitive, num_trips competitive
    # whether it's a short/medium/long route, etc
    '''
    competitive_stats_by_route = get_competitive_routes()
    
    by_route_with_competitive_stats = pd.merge(
        by_route,
        competitive_stats_by_route,
        on = ["calitp_itp_id", "route_id"],
        # do left join to keep all the stop_times and trips info
        # inner join means that those routes that didn't have Google Map 
        # responses will get left out
        how = "left",
    )
    '''

