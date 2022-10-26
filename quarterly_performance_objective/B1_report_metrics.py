"""
Functions to calculate summary stats for report.

Two reports: current quarter, historical report.
Since we need to the same dataset across notebooks, 
generate the various pieces needed in the report too.
"""
import geopandas as gpd
import pandas as pd

from shared_utils import geography_utils
from update_vars import ANALYSIS_DATE, BUS_SERVICE_GCS

def add_percent(df: pd.DataFrame, col_list: list) -> pd.DataFrame:
    """
    Create columns with pct values. 
    """
    for c in col_list:
        new_col = f"pct_{c}"
        df[new_col] = (df[c] / df[c].sum()).round(3)
        df[c] = df[c].round(0)
        
    return df

#https://stackoverflow.com/questions/23482668/sorting-by-a-custom-list-in-pandas
def sort_by_column(df: pd.DataFrame, 
                   col: str = "category", 
                   sort_key: list = ["on_shn", "intersects_shn", "other"]
                  ) -> pd.DataFrame:
    # Custom sort order for categorical variable
    df = df.sort_values(
        col, key=lambda c: c.map(lambda e: sort_key.index(e)))
    return df


def clean_up_category_values(df: pd.DataFrame) -> pd.DataFrame:
    category_values = {
        "on_shn": "On SHN", 
        "intersects_shn": "Intersects SHN",
        "other": "Other"
    }
    
    df = df.assign(
        category = df.category.map(category_values)
    )
    
    return df


def get_service_hours_summary_table(df: pd.DataFrame)-> pd.DataFrame: 
    """
    Aggregate by parallel/on_shn/other category.
    Calculate number and pct of service hours, routes.
    """
    summary = geography_utils.aggregate_by_geography(
        df, 
        group_cols = ["category"],
        sum_cols = ["service_hours", "unique_route"],
    ).astype({"service_hours": int, "unique_route": int})
    
    summary = add_percent(summary, ["service_hours", "unique_route"])
    
    summary = sort_by_column(summary).pipe(clean_up_category_values)
    
    summary = summary.assign(
        service_hrs_per_route = round(summary.service_hours / 
                                      summary.unique_route, 2)
    )
    
    return summary


def get_delay_summary_table(df: pd.DataFrame) -> pd.DataFrame:
    # Note: merge_delay both narrows down the dataset quite a bit
    delay_df = df[df.merge_delay=="both"]

    delay_summary = geography_utils.aggregate_by_geography(
        delay_df, 
        group_cols = ["category"],
        sum_cols = ["delay_hours", "unique_route"],
    ).astype({"unique_route": int})
    
    delay_summary = (sort_by_column(delay_summary)
                     .pipe(clean_up_category_values)
                    )


    delay_summary = delay_summary.assign(
        delay_hours_per_route = round(delay_summary.delay_hours / 
                                      delay_summary.unique_route, 2)
    )
    
    delay_summary = add_percent(delay_summary, ["delay_hours", "unique_route"])
    
    return delay_summary


def by_district_on_shn_breakdown(df: pd.DataFrame, sum_cols: list) -> pd.DataFrame:
    """
    Get service hours or delay hours by district, and 
    add in percent and average metrics.
    """
    by_district = geography_utils.aggregate_by_geography(
        df[df.category=="on_shn"],
        group_cols = ["District"],
        sum_cols = sum_cols
    ).astype(int)

    by_district = (add_percent(
        by_district, 
        sum_cols)
        .sort_values("District")
    )
    
    pct_cols = [f"pct_{c}" for c in sum_cols]
    
    for c in pct_cols:
        by_district[c] = by_district[c].round(3)
    
    # Calculate average
    if "service_hours" in by_district.columns:
        numerator_col = "service_hours"
    elif "delay_hours" in by_district.columns:
        numerator_col = "delay_hours"
    
    by_district = by_district.assign(
        avg = by_district[numerator_col].divide(
            by_district.unique_route).round(1)
    ).rename(columns = {"avg": f"avg_{numerator_col}"})
    
    return by_district


def route_type_names(row): 
    if row.route_type in ['0', '1', '2']:
        return "Rail"
    elif row.route_type == '3':
        return "Bus"
    elif row.route_type == '4':
        return "Ferry"
    else:
        return "Unknown"

    
def prep_data_for_report(analysis_date: str) -> gpd.GeoDataFrame:
    df = gpd.read_parquet(
        f"{BUS_SERVICE_GCS}routes_categorized_with_delay_{analysis_date}.parquet")
    
    # Some interest in excluding modes like rail from District 4
    df = df.assign(
        route_type_name = df.apply(lambda x: route_type_names(x), axis=1),
        delay_hours = round(df.delay_seconds / 60 ** 2, 2)
    ).drop(columns = "delay_seconds")

    #df[df.category=="on_shn"].route_type_name.value_counts()
    # This shows that only Bus and Unknown are present for on_shn
    
    # Should I subset to df[df._merge=="both"]?
    # both means that it found a corresponding match in itp_id-route_id 
    # since it's been aggregated up to route_id level (shape_id can mismatch more easily)
    # Decide here, this is the subset of data I will use for rest of notebook
    plot_df = df[df._merge=="both"].reset_index(drop=True)
    
    return plot_df
