# Regular
import calitp_data_analysis.magics
import geopandas as gpd
import pandas as pd
from calitp_data_analysis.sql import to_snakecase
import numpy as np

# Project Specific Packages
from segment_speed_utils.project_vars import (COMPILED_CACHED_VIEWS, RT_SCHED_GCS, SCHED_GCS)
from shared_utils import catalog_utils, rt_dates, rt_utils
import _report_utils 
import _operators_prep as op_prep
from segment_speed_utils import helpers

# Readable Dictionary
import yaml
with open("readable.yml") as f:
    readable_dict = yaml.safe_load(f)
GTFS_DATA_DICT = catalog_utils.get_catalog("gtfs_analytics_data")

# Charts & Maps
from calitp_data_analysis import calitp_color_palette as cp
import altair as alt
import ipywidgets
from IPython.display import HTML, Markdown, display
with open("color_palettes.yml") as f:
    color_dict = yaml.safe_load(f)

"""
Data
"""
def organization_name_crosswalk(organization_name: str) -> str:
    """
    Used to match organization_name field with name.
    """
    schd_vp_url = f"{GTFS_DATA_DICT.digest_tables.dir}{GTFS_DATA_DICT.digest_tables.route_schedule_vp}.parquet"
    df = pd.read_parquet(
        schd_vp_url, filters=[[("organization_name", "==", organization_name)]],
    )
    
    # Get most recent name
    df = df.sort_values(by = ['service_date'], ascending = False)
    name = df.name.values[0]
    return name

def load_operator_map(name:str)->gpd.GeoDataFrame:
    """
    Load geodataframe with all of the operator's routes.
    """
    op_routes_url = f"{GTFS_DATA_DICT.digest_tables.dir}{GTFS_DATA_DICT.digest_tables.operator_routes_map}.parquet"
    op_routes_gdf = gpd.read_parquet(
    op_routes_url,
    filters=[[("name", "==", name)]])
    
    # Find the most recent available geography for each route
    op_routes_gdf = op_routes_gdf.sort_values(by = ["service_date"], ascending = False)
    op_routes_gdf = op_routes_gdf.drop_duplicates(
    subset=["route_long_name", "route_short_name", "route_combined_name"]
    )
    op_routes_gdf = op_routes_gdf.drop(columns = ['service_date'])
    
    # Rename dataframe
    op_routes_gdf.columns = op_routes_gdf.columns.map(_report_utils.replace_column_names)
    return op_routes_gdf

def get_counties():
    ca_gdf = "https://opendata.arcgis.com/datasets/8713ced9b78a4abb97dc130a691a8695_0.geojson"
    my_gdf = to_snakecase(gpd.read_file(f"{ca_gdf}"))[["county_name", "geometry"]]

    return my_gdf

"""
Data Manipulation
Change dataframes from long to wide
"""
def route_typology(df: pd.DataFrame)->pd.DataFrame:
    """
    Transform dataframe to display
    route types in a pie chart.
    """
    route_type_cols = [
       '# Downtown Local Route Types',
       '# Local Route Types', '# Coverage Route Types', '# Rapid Route Types',
       '# Express Route Types', '# Rail Route Types'
    ]
    df = df[route_type_cols]
    df2 = df.T.reset_index()
    df2.columns = ['route_type','total_routes']
    return df2

def concat_all_columns(df):
    # Concatenate all columns into a new column called 'all'
    df['all'] = df.apply(lambda row: ', '.join(row.astype(str)), axis=1)

    return df

def counties_served(gdf:gpd.GeoDataFrame)->pd.DataFrame:
    """
    Find which counties an operator serves.
    """
    ca_counties = get_counties()
    counties_served = gpd.sjoin(
    gdf,
    ca_counties.to_crs(gdf.crs),
    how="inner",
    predicate="intersects").drop(columns="index_right")
    
    counties_served = (counties_served[["county_name"]]
                       .drop_duplicates()
                       .sort_values(by = ["county_name"])
                       .reset_index(drop = True)
                      )
    counties_served = counties_served.T
    counties_served = concat_all_columns(counties_served)
    return counties_served

def shortest_longest_route(gdf:gpd.GeoDataFrame)->pd.DataFrame:
    df = (
    gdf[["Route", "Service Miles"]]
    .sort_values(by=["Service Miles"])
    .iloc[[0, -1]])
    
    return df

"""
Charts & Maps
"""
def create_bg_service_chart():
    """
    Create a shaded background for the Service Hour Chart
    by time period. 
    """
    cutoff = pd.DataFrame(
    {
        "start": [0, 4, 7, 10, 15, 19],
        "stop": [3.99, 6.99, 9.99, 14.99, 18.99, 24],
        "time_period": [
            "Owl:12-3:59AM",
            "Early AM:4-6:59AM",
            "AM Peak:7-9:59AM",
            "Midday:10AM-2:59PM",
            "PM Peak:3-7:59PM",
            "Evening:8-11:59PM",
        ],
    }
    )
    
    # Sort legend by time, 12am starting first. 
    chart = alt.Chart(cutoff.reset_index()).mark_rect(opacity=0.15).encode(
    x="start",
    x2="stop",
    y=alt.value(0),  # pixels from top
    y2=alt.value(250),  # pixels from top
    color=alt.Color(
        "time_period:N",
        sort = (
            [
                "Owl:12-3:59AM",
                "Early AM:4-6:59AM",
                "AM Peak:7-9:59AM",
                "Midday:10AM-2:59PM",
                "PM Peak:3-7:59PM",
                "Evening:8-11:59PM",
            ]
        ),
        title=_report_utils.labeling("time_period"),
        scale=alt.Scale(range=color_dict["full_color_scale"]),
    ))
    
    return chart

def create_service_hour_chart(df:pd.DataFrame,
                              day_type:str,
                              y_col:str,
                              subtitle:str):
    # Create an interactive legend so you can view
    # lines by year 
    selection = alt.selection_point(fields=['Month'], bind='legend')
    
    # Create the main line chart
    df = df.loc[df["Weekend or Weekday"] == day_type].reset_index(drop = True)
    
    # Create a new title that incorporates day type
    title = readable_dict["daily_scheduled_hour"]["title"]
    title = title + ' for ' + day_type

    main_chart = (
    alt.Chart(df)
    .mark_line(size=3)
    .encode(
        x=alt.X("Departure Hour", 
                title=_report_utils.labeling("Departure Hour in Military Time")),
        y=alt.Y(y_col,
               title = _report_utils.labeling(y_col)),
        color=alt.Color(
            "Month",
            scale=alt.Scale(range=color_dict["full_color_scale"]),  # Specify desired order
        ),
        opacity=alt.condition(selection, alt.value(1), alt.value(0.2)),
        tooltip=list(df.columns),
    )
    .properties(
        width=400,
        height=250,
        title={"text": title, 
               "subtitle": subtitle},
    )
    .add_params(selection)
    )
    
    # Load background chart
    bg_chart = create_bg_service_chart()
    
    # Combine
    final_chart = (main_chart + bg_chart).properties(
    resolve=alt.Resolve(
        scale=alt.LegendResolveMap(color=alt.ResolveMode("independent"))
    )
    )
    
    return final_chart

def basic_bar_chart(df: pd.DataFrame, x_col: str, y_col: str,
                    title: str, subtitle:str):
    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X(x_col, title=_report_utils.labeling(x_col)),
            y=alt.Y(y_col, title=_report_utils.labeling(y_col)),
            color=alt.Color(
               y_col,
                legend = None,
                title=_report_utils.labeling(y_col),
                scale=alt.Scale(
                    range=color_dict["tri_color"],
                )
        ),
        tooltip = [x_col, y_col])
        .properties(
            width=400,
            title={
                "text": [title],
                "subtitle": [subtitle],
            }
        )
    )
    return chart

def basic_pie_chart(df: pd.DataFrame, 
                    color_col: str, 
                    theta_col: str, 
                    title: str,
                    subtitle:str):
    chart = (
        alt.Chart(df)
        .mark_arc()
        .encode(
            theta=theta_col,
            color=alt.Color(
                color_col, 
                title=_report_utils.labeling(color_col),
                scale=alt.Scale(range=color_dict["full_color_scale"])
            ),
            tooltip=df.columns.tolist(),
        ).properties(
            width=400,
            height=250,
            title={
                "text": [title],
                "subtitle": [subtitle],
            }
        ))
    
    return chart

"""
Maps
"""
def plot_route(route):
    filtered_gdf = gdf[gdf["Route"] == route]
    display(filtered_gdf.explore(column="Route", cmap = "Spectral",
    tiles="CartoDB positron",
    width=400,
    height=250,
    style_kwds={"weight": 3},
    legend=False,
    tooltip=["Route", "Service Miles"]))
