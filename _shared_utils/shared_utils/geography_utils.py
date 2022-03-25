"""
Utility functions for geospatial data.
Some functions for dealing with census tract or other geographic unit dfs.
"""
import os

import geopandas as gpd
import pandas as pd
import shapely
from calitp.tables import tbl
from siuba import *

os.environ["CALITP_BQ_MAX_BYTES"] = str(50_000_000_000)

WGS84 = "EPSG:4326"
CA_StatePlane = "EPSG:2229"  # units are in feet
CA_NAD83Albers = "EPSG:3310"  # units are in meters

SQ_MI_PER_SQ_M = 3.86 * 10 ** -7
FEET_PER_MI = 5_280
SQ_FT_PER_SQ_MI = 2.788 * 10 ** 7


def aggregate_by_geography(
    df,
    group_cols,
    sum_cols=[],
    mean_cols=[],
    count_cols=[],
    nunique_cols=[],
    rename_cols=False,
):
    """
    df: pandas.DataFrame or geopandas.GeoDataFrame.,
        The df on which the aggregating is done.
        If it's a geodataframe, it must exclude the tract's geometry column

    group_cols: list.
        List of columns to do the groupby, but exclude geometry.
    sum_cols: list.
        List of columns to calculate a sum with the groupby.
    mean_cols: list.
        List of columns to calculate an average with the groupby
        (beware: may want weighted averages and not simple average!!).
    count_cols: list.
        List of columns to calculate a count with the groupby.
    nunique_cols: list.
        List of columns to calculate the number of unique values with the groupby.
    rename_cols: boolean.
        Defaults to False. If True, will rename columns in sum_cols to have suffix `_sum`,
        rename columns in mean_cols to have suffix `_mean`, etc.

    Returns a pandas.DataFrame or geopandas.GeoDataFrame (same as input).
    """
    final_df = df[group_cols].drop_duplicates().reset_index()

    def aggregate_and_merge(df, final_df, group_cols, agg_cols, AGGREGATE_FUNCTION):

        agg_df = df.pivot_table(
            index=group_cols, values=agg_cols, aggfunc=AGGREGATE_FUNCTION
        ).reset_index()

        if rename_cols is True:
            # https://stackoverflow.com/questions/34049618/how-to-add-a-suffix-or-prefix-to-each-column-name
            # Why won't .add_prefix or .add_suffix work?
            for c in agg_cols:
                agg_df = agg_df.rename(columns={c: f"{c}_{AGGREGATE_FUNCTION}"})

        final_df = pd.merge(final_df, agg_df, on=group_cols, how="left", validate="1:1")
        return final_df

    if len(sum_cols) > 0:
        final_df = aggregate_and_merge(df, final_df, group_cols, sum_cols, "sum")

    if len(mean_cols) > 0:
        final_df = aggregate_and_merge(df, final_df, group_cols, mean_cols, "mean")

    if len(count_cols) > 0:
        final_df = aggregate_and_merge(df, final_df, group_cols, count_cols, "count")

    if len(nunique_cols) > 0:
        final_df = aggregate_and_merge(
            df, final_df, group_cols, nunique_cols, "nunique"
        )

    return final_df.drop(columns="index")


def attach_geometry(df, geometry_df, merge_col=["Tract"], join="left"):
    """
    df: pandas.DataFrame
        The df that needs tract geometry added.
    geometry_df: geopandas.GeoDataFrame
        The gdf that supplies the geometry.
    merge_col: list.
        List of columns to do the merge on.
    join: str.
        Specify whether it's a left, inner, or outer join.

    Returns a geopandas.GeoDataFrame
    """
    gdf = pd.merge(
        geometry_df.to_crs(WGS84),
        df,
        on=merge_col,
        how=join,
    )

    return gdf


def make_routes_gdf(SELECTED_DATE, CRS="EPSG:4326"):
    """
    Parameters:

    SELECTED_DATE: str or datetime
        Ex: '2022-1-1' or datetime.date(2022, 1, 1)
    CRS: str, a projected coordinate reference system.
        Defaults to EPSG:4326 (WGS84)
    EXCLUDE_ITP_ID: list
            Defaults to exclude ITP_ID==200, which is an aggregate Bay Area feed
    INCLUDE_ITP_ID: list or "all"
            Defaults to all ITP_IDs except ITP_ID==200.
            For a subset of operators, include a list, such as [182, 100].
    All operators for selected date: ~x minutes
    """

    df = (
        tbl.views.gtfs_schedule_dim_shapes()
        >> filter(
            _.calitp_extracted_at <= SELECTED_DATE, _.calitp_deleted_at > SELECTED_DATE
        )
        >> filter(_.calitp_itp_id != 200)
        >> select(_.calitp_itp_id, _.calitp_url_number, _.shape_id)
        >> inner_join(
            _,
            tbl.views.gtfs_schedule_dim_shapes_geo(),
            ["calitp_itp_id", "calitp_url_number", "shape_id"],
        )
        >> collect()
    )

    # Laurie's example: https://github.com/cal-itp/data-analyses/blob/752eb5639771cb2cd5f072f70a06effd232f5f22/gtfs_shapes_geo_examples/example_shapes_geo_handling.ipynb
    # have to convert to linestring
    def make_linestring(x):

        # shapely errors if the array contains only one point
        if len(x) > 1:
            # each point in the array is wkt
            # so convert them to shapely points via list comprehension
            as_wkt = [shapely.wkt.loads(i) for i in x]
            return shapely.geometry.LineString(as_wkt)

    # apply the function
    df["geometry"] = df.pt_array.apply(make_linestring)

    # convert to geopandas; geometry column contains the linestring
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs=WGS84)

    # Project, if necessary
    gdf = gdf.to_crs(CRS)

    return gdf


# Function to take transit stop point data and create lines
def make_routes_shapefile(ITP_ID_LIST=[], CRS="EPSG:4326", alternate_df=None):
    """
    Parameters:
    ITP_ID_LIST: list. List of ITP IDs found in agencies.yml
    CRS: str. Default is WGS84, but able to re-project to another CRS.

    Returns a geopandas.GeoDataFrame, where each line is the operator-route-line geometry.
    """

    all_routes = gpd.GeoDataFrame()

    for itp_id in ITP_ID_LIST:
        if alternate_df is None:
            shapes = (
                tbl.gtfs_schedule.shapes()
                >> filter(_.calitp_itp_id == int(itp_id))
                >> collect()
            )

        elif alternate_df is not None:
            shapes = alternate_df.copy()

            # With historical gtfs_schedule_type2.shapes table, there is a valid shape_id
            if shapes.shape_id.isnull().sum() == 0:
                pass
            else:
                # shape_id is None, which will throw up an error later on when there's groupby
                # So, create shape_id and fill it in with route_id info, but only if it's missing
                # To flag these, shape_id as a column wouldn't even exist.
                if "shape_id" not in shapes.columns:
                    shapes = shapes.assign(
                        shape_id=shapes.route_id,
                    )
                else:
                    # This handles operators where most of their shape_ids are valid
                    # Let's just drop missing ones.
                    shapes = shapes[shapes.shape_id.notna()].reset_index(drop=True)

        # Make a gdf
        shapes = gpd.GeoDataFrame(
            shapes,
            geometry=gpd.points_from_xy(shapes.shape_pt_lon, shapes.shape_pt_lat),
            crs=WGS84,
        )

        # Count the number of stops for a given shape_id
        # Must be > 1 (need at least 2 points to make a line)
        shapes = shapes.assign(
            num_stops=(
                shapes.groupby("shape_id")["shape_pt_sequence"].transform("count")
            )
        )

        # Drop the shape_ids that can't make a line
        shapes = shapes[shapes.num_stops > 1].reset_index(drop=True)

        # Now, combine all the stops by stop sequence, and create linestring
        for route in shapes.shape_id.unique():
            single_shape = (
                shapes
                >> filter(_.shape_id == route)
                >> mutate(shape_pt_sequence=_.shape_pt_sequence.astype(int))
                # arrange in the order of stop sequence
                >> arrange(_.shape_pt_sequence)
            )

            # Convert from a bunch of points to a line (for a route, there are multiple points)
            route_line = shapely.geometry.LineString(list(single_shape["geometry"]))
            single_route = single_shape[
                ["calitp_itp_id", "calitp_url_number", "shape_id"]
            ].iloc[
                [0]
            ]  # preserve info cols
            single_route["geometry"] = route_line
            single_route = gpd.GeoDataFrame(single_route, crs=WGS84)

            # https://stackoverflow.com/questions/15819050/pandas-dataframe-concat-vs-append/48168086
            all_routes = pd.concat(
                [all_routes, single_route], ignore_index=True, axis=0
            )

    all_routes = (
        all_routes.to_crs(CRS)
        .sort_values(["calitp_itp_id", "shape_id"])
        .drop_duplicates()
        .reset_index(drop=True)
    )

    return all_routes


# Function to deal with edge cases where operators do not submit the optional shapes.txt
# Use stops data / stop sequence to handle
def make_routes_line_geom_for_missing_shapes(df, CRS="EPSG:4326"):
    """
    Parameters:
    df: pandas.DataFrame.
        Compile a dataframe from gtfs_schedule_trips.
        Find the trips that aren't in `shapes.txt`.
        https://github.com/cal-itp/data-analyses/blob/main/traffic_ops/create_routes_data.py#L63-L69
        Use that dataframe here.

    CRS: str, a projected coordinated reference system.
            Defaults to EPSG:4326 (WGS84)
    """
    if "shape_id" not in df.columns:
        df = df.assign(shape_id=df.route_id)

    # Make a gdf
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df.stop_lon, df.stop_lat),
        crs=WGS84,
    )

    # Count the number of stops for a given shape_id
    # Must be > 1 (need at least 2 points to make a line)
    gdf = gdf.assign(
        num_stops=(gdf.groupby("shape_id")["stop_sequence"].transform("count"))
    )

    # Drop the shape_ids that can't make a line
    gdf = (
        gdf[gdf.num_stops > 1]
        .reset_index(drop=True)
        .assign(stop_sequence=gdf.stop_sequence.astype(int))
        .drop(columns="num_stops")
    )

    # shapely make linestring with groupby
    # https://gis.stackexchange.com/questions/366058/pandas-dataframe-to-shapely-linestring-using-groupby-sortby
    group_cols = ["calitp_itp_id", "calitp_url_number", "shape_id"]

    gdf2 = (
        gdf.sort_values(group_cols + ["stop_sequence"])
        .groupby(group_cols)["geometry"]
        .apply(lambda x: LineString(x.tolist()))
    )

    gdf2 = gpd.GeoDataFrame(gdf2, geometry="geometry", crs=WGS84)
    gdf2 = (
        gdf2.to_crs(CRS)
        .sort_values(["calitp_itp_id", "calitp_url_number", "shape_id"])
        .drop_duplicates()
        .reset_index(drop=True)
    )

    return gdf2


def create_point_geometry(
    df, longitude_col="stop_lon", latitude_col="stop_lat", crs=WGS84
):
    """
    Parameters:
    df: pandas.DataFrame to turn into geopandas.GeoDataFrame,
        default dataframe in mind is gtfs_schedule.stops

    longitude_col: str, column name corresponding to longitude
                    in gtfs_schedule.stops, this column is "stop_lon"

    latitude_col: str, column name corresponding to latitude
                    in gtfs_schedule.stops, this column is "stop_lat"

    crs: str, coordinate reference system for point geometry
    """
    df = df.assign(
        geometry=gpd.points_from_xy(df[longitude_col], df[latitude_col], crs=crs)
    )

    gdf = gpd.GeoDataFrame(df)
    return gdf
