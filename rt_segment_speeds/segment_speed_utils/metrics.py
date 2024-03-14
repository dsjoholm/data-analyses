"""
Define the metrics we can derive for 
segment speeds, RT vs schedule, etc.
"""
import pandas as pd

from typing import Literal

from segment_speed_utils import segment_calcs

def weighted_average_speeds_across_segments(
    df: pd.DataFrame,
    group_cols: list
) -> pd.DataFrame: 
    """
    We can use our segments and the deltas within a trip
    to calculate the trip-level average speed, or
    the route-direction-level average speed.
    But, we want a weighted average, using the raw deltas
    instead of mean(speed_mph), since segments can be varying lengths.
    """
    avg_speeds_peak = (df.groupby(group_cols + ["peak_offpeak"], 
                      observed=True, group_keys=False)
           .agg({
               "meters_elapsed": "sum",
               "sec_elapsed": "sum",
           }).reset_index()
          )
    
    avg_speeds_peak = segment_calcs.speed_from_meters_elapsed_sec_elapsed(
        avg_speeds_peak)
            
    # For all aggregations above the trip level, continue on
    if "trip_instance_key" not in group_cols:
        avg_speeds_allday = (df.groupby(group_cols, 
                                        observed=True, group_keys=False)
                             .agg({
                                 "meters_elapsed": "sum",
                                 "sec_elapsed": "sum",
                             }).reset_index()
                            )

        avg_speeds_allday = segment_calcs.speed_from_meters_elapsed_sec_elapsed(
            avg_speeds_allday
        ).assign(
            peak_offpeak = "all_day"
        )
    
        avg_speeds = pd.concat(
            [avg_speeds_peak, avg_speeds_allday],
            axis=0, ignore_index = True
        ).rename(
            columns = {"peak_offpeak": "time_period"}
        )

        return avg_speeds
    
    # A trip level dataset cannot be aggregated to peak/offpeak/all_day
    else:
        return avg_speeds_peak


def derive_rt_vs_schedule_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add metrics and numeric rounding.
    """
    integrify = ["vp_in_shape", "total_vp"]
    df[integrify] = df[integrify].fillna(0).astype("int")
    
    df = df.assign(
        vp_per_minute = df.total_vp / df.rt_service_minutes,
        pct_in_shape = df.vp_in_shape / df.total_vp,
        pct_rt_journey_vp = df.minutes_atleast1_vp / df.rt_service_minutes,
        pct_rt_journey_atleast2_vp = df.minutes_atleast2_vp / df.rt_service_minutes,
        pct_sched_journey_atleast1_vp = (df.minutes_atleast1_vp / 
                                         df.scheduled_service_minutes),
        pct_sched_journey_atleast2_vp = (df.minutes_atleast2_vp / 
                                         df.scheduled_service_minutes),
    )
    
    two_decimal_cols = [
        "vp_per_minute", "rt_service_minutes", 
    ]
    
    df[two_decimal_cols] = df[two_decimal_cols].round(2)
    
    three_decimal_cols = [
        c for c in df.columns if "pct_" in c
    ]
    
    df[three_decimal_cols] = df[three_decimal_cols].round(3)

    # Mask percents for any values above 100%
    # Scheduled service minutes can be assumed to be shorter than 
    # RT service minutes, so there can be more minutes with vp data available
    mask_me = [c for c in df.columns if 
               ("pct_sched_journey" in c) or 
               # check when this would happen in route direction aggregation
               ("pct_rt_journey" in c)]
    for c in mask_me:
        df[c] = df[c].mask(df[c] > 1, 1)

    return df    


def calculate_weighted_average_vp_schedule_metrics(
    df: pd.DataFrame, 
    group_cols: list,
) -> pd.DataFrame:
    
    sum_cols = [
        "minutes_atleast1_vp",
        "minutes_atleast2_vp",
        "rt_service_minutes",
        "scheduled_service_minutes",
        "total_vp",
        "vp_in_shape",
    ]

    count_cols = ["trip_instance_key"]
    
    df2 = (
        df.groupby(group_cols,
                   observed=True, group_keys=False)
        .agg({
            **{e: "sum" for e in sum_cols}, 
            **{e: "count" for e in count_cols}}
        ).reset_index()
        .rename(columns = {"trip_instance_key": "n_trips"})
    )
    
    return df2


def concatenate_peak_offpeak_allday_averages(
    df: pd.DataFrame, 
    group_cols: list,
    metric_type: Literal["segment_speeds", "rt_vs_schedule"]
) -> pd.DataFrame:
    """
    Calculate average speeds for all day and
    peak_offpeak.
    Concatenate these, so that speeds are always calculated
    for the same 3 time periods.
    """
    if metric_type == "segment_speeds":
        avg_peak = segment_calcs.calculate_avg_speeds(
            df,
            group_cols + ["peak_offpeak"]
        )

        avg_allday = segment_calcs.calculate_avg_speeds(
            df,
            group_cols
        ).assign(peak_offpeak = "all_day")
    
    elif metric_type == "rt_vs_schedule":
        avg_peak = calculate_weighted_average_vp_schedule_metrics(
            df,
            group_cols + ["peak_offpeak"]
        )
        
        avg_allday = calculate_weighted_average_vp_schedule_metrics(
            df,
            group_cols
        ).assign(peak_offpeak = "all_day")
        
    else:
        print(f"Valid metric types: ['segment_speeds', 'rt_vs_schedule']")
        
    # Concatenate so that every segment has 3 time periods: peak, offpeak, and all_day
    avg_metrics = pd.concat(
        [avg_peak, avg_allday], 
        axis=0, ignore_index = True
    ).rename(
        columns = {"peak_offpeak": "time_period"}
    )
        
    return avg_metrics