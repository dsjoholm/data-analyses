"""
Functions for applying shapely project and interpolation.
Move our shapes (linestrings) and stops (points) from coordinates
to numpy arrays with numeric values (shape_meters) and vice versa.
"""
import dask.array as da
import dask.dataframe as dd
import dask_geopandas as dg
import geopandas as gpd
import numpy as np
import pandas as pd

from shared_utils import rt_utils
from segment_speed_utils.project_vars import PROJECT_CRS

def add_arrowized_geometry(gdf: dg.GeoDataFrame) -> dg.GeoDataFrame:
    """
    Add a column where the segment is arrowized.
    """
    if isinstance(gdf, gpd.GeoDataFrame):
        gdf = dg.from_geopandas(gdf, npartitions=3) 
        
    gdf = gdf.assign(
        geometry_arrowized = gdf.apply(
            lambda x: rt_utils.try_parallel(x.geometry), 
            axis=1, 
            meta = ("geometry_arrowized", "geometry")
        )
    )
    
    gdf = gdf.assign(
        geometry_arrowized = gdf.apply(
            lambda x: rt_utils.arrowize_segment(
                x.geometry_arrowized, buffer_distance = 20),
            axis = 1,
            meta = ('geometry_arrowized', 'geometry')
        )
    )

    return gdf


def project_point_geom_onto_linestring(
    shape_geoseries: gpd.GeoSeries,
    point_geoseries: gpd.GeoSeries,
    get_dask_array: bool = True
) -> pd.Series:
    """
    Use shapely.project to turn point coordinates into numeric.
    The point coordinates will be converted to the distance along the linestring.
    https://shapely.readthedocs.io/en/stable/manual.html?highlight=project#object.project
    https://gis.stackexchange.com/questions/306838/snap-points-shapefile-to-line-shapefile-using-shapely
    """
    shape_meters_geoseries = shape_geoseries.project(point_geoseries)
    
    if get_dask_array:
        shape_meters_geoseries = da.array(shape_meters_geoseries)
    
    # To add this as a column to a dask df
    # https://www.appsloveworld.com/coding/dataframe/6/add-a-dask-array-column-to-a-dask-dataframe
    return shape_meters_geoseries


def linear_reference_vp_against_segment(
    vp: dd.DataFrame, 
    segments: gpd.GeoDataFrame, 
    segment_identifier_cols: list
) -> dd.DataFrame:
    """
    Do linear referencing and calculate `shape_meters` for the 
    enter/exit points on the segment. 
    
    From Eric: projecting the stop's point geom onto the shape_id's line geom
    https://github.com/cal-itp/data-analyses/blob/f4c9c3607069da6ea96e70c485d0ffe1af6d7a47/rt_delay/rt_analysis/rt_parser.py#L102-L103
    
    This allows us to calculate the distance_elapsed.
    
    Return dd.DataFrame because geometry makes the file huge.
    Merge in segment geometry later before plotting.
    """
    
    if isinstance(segments, dg.GeoDataFrame):
        segments = segments.compute()
    
    # https://stackoverflow.com/questions/71685387/faster-methods-to-create-geodataframe-from-a-dask-or-pandas-dataframe
    # https://github.com/geopandas/dask-geopandas/issues/197
    vp = vp.assign(
        geometry = dg.points_from_xy(vp, "lon", "lat", crs = PROJECT_CRS), 
    )
    
    # Refer to the geometry column by name
    vp_gddf = dg.from_dask_dataframe(
        vp, 
        geometry="geometry"
    )
    
    linear_ref_vp_to_shape = dd.merge(
        vp_gddf, 
        segments[segments.geometry.notna()
                ][segment_identifier_cols + ["geometry"]],
        on = segment_identifier_cols,
        how = "inner"
    )
    
    # Convert to geoseries so that we can do the project
    vp_geoseries = gpd.GeoSeries(linear_ref_vp_to_shape.geometry_x.compute())
    shape_geoseries = gpd.GeoSeries(linear_ref_vp_to_shape.geometry_y.compute())
    
    # Project, save results, then convert to dask array, 
    # otherwise can't add a column to the dask df
    shape_meters_geoseries = project_point_geom_onto_linestring(
        shape_geoseries,
        vp_geoseries,
        get_dask_array=True
    )

    # https://www.appsloveworld.com/coding/dataframe/6/add-a-dask-array-column-to-a-dask-dataframe
    linear_ref_vp_to_shape['shape_meters'] = shape_meters_geoseries
    
    linear_ref_df = (linear_ref_vp_to_shape.drop(
        columns = ["geometry_x", "geometry_y",
                   "lon", "lat"])
                     .drop_duplicates()
                     .reset_index(drop=True)
    )
    
    return linear_ref_df