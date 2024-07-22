import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from scipy.spatial import KDTree

from calitp_data_analysis.geography_utils import WGS84
from segment_speed_utils import gtfs_schedule_wrangling, wrangle_shapes     
from segment_speed_utils.project_vars import SEGMENT_GCS, GTFS_DATA_DICT

geo_const_meters = 6_371_000 * np.pi / 180
geo_const_miles = 3_959_000 * np.pi / 180

def nearest_snap(
    line: shapely.LineString, 
    point: shapely.Point,
    k_neighbors: int = 1
) -> np.ndarray:
    """
    Based off of this function,
    but we want to return the index value, rather than the point.
    https://github.com/UTEL-UIUC/gtfs_segments/blob/main/gtfs_segments/geom_utils.py
    """
    line = np.asarray(line.coords)
    point = np.asarray(point.coords)
    tree = KDTree(line)
    
    # np_dist is array of distances of result (let's not return it)
    # np_inds is array of indices of result
    _, np_inds = tree.query(
        point, workers=-1, k=k_neighbors, 
    )
    
    return np_inds.squeeze()
    

def add_nearest_vp_idx(
    vp_linestring: shapely.LineString, 
    stop: shapely.Point, 
    vp_idx_arr: np.ndarray
) -> int:
    """
    Index into where the nearest vp is to the stop,
    and return that vp_idx value from the vp_idx array.
    """
    idx = nearest_snap(vp_linestring, stop)
    
    return vp_idx_arr[idx]


def add_trio(
    nearest_value: int,
    vp_idx_arr: np.ndarray,
    timestamp_arr: np.ndarray,
    coords_arr: np.ndarray,
) -> tuple[np.ndarray]:
    """
    Try to grab at least 2 vp_idx, but optimally 3 vp_idx,
    including the nearest_vp_idx to 
    act as boundaries to interpolate against.
    3 points hopefully means 2 intervals where the stop could occur in
    to give us successful interpolation result.
    
    We don't have a guarantee that the nearest_vp_idx is before
    the stop, so let's just keep more boundary points.
    """
    array_length = len(vp_idx_arr)
    try:
        start_idx = np.where(vp_idx_arr == nearest_value)[0][0]
    
    # Just in case we don't have any vp_idx_arr, set to zero and
    # use condition later to return empty array
    except:
        start_idx = 0

    # if we only have 2 values, we want to return all the possibilities
    if array_length <= 2:
        return vp_idx_arr, timestamp_arr, coords_arr
    
    # if it's the first value of the array 
    # and array is long enough for us to grab another value    
    elif (start_idx == 0) and (array_length > 2):
        start_pos = start_idx
        end_pos = start_idx + 3
        return (vp_idx_arr[start_pos: end_pos], 
                timestamp_arr[start_pos: end_pos], 
                coords_arr[start_pos: end_pos])
    
    # if it's the last value in the array, still grab 3 vp_idx
    elif (start_idx == array_length - 1) and (array_length > 0):
        start_pos = start_idx - 2
        return (vp_idx_arr[start_pos: ], 
                timestamp_arr[start_pos: ],
                coords_arr[start_pos: ]
               )
    
    # (start_idx > 0) and (array_length > 2):
    else: 
        start_pos = start_idx - 1
        end_pos = start_idx + 2
        return (vp_idx_arr[start_pos: end_pos], 
                timestamp_arr[start_pos: end_pos],
                coords_arr[start_pos: end_pos]
               )

    
def merge_stop_vp_for_nearest_neighbor(
    stop_times: gpd.GeoDataFrame,
    analysis_date: str,
    **kwargs
) -> gpd.GeoDataFrame:
    VP_NN = GTFS_DATA_DICT.speeds_tables.vp_nearest_neighbor
    
    vp_condensed = gpd.read_parquet(
        f"{SEGMENT_GCS}{VP_NN}_{analysis_date}.parquet",
        columns = ["trip_instance_key", 
                   "vp_idx", "vp_primary_direction", 
                   "geometry"],
        **kwargs
    ).to_crs(WGS84)

    gdf = pd.merge(
        stop_times.rename(
            columns = {
                "geometry": "stop_geometry"}
        ).set_geometry("stop_geometry").to_crs(WGS84),
        vp_condensed.rename(
            columns = {
                "vp_primary_direction": "stop_primary_direction",
                "geometry": "vp_geometry"
            }),
        on = ["trip_instance_key", "stop_primary_direction"],
        how = "inner"
    )
        
    return gdf


def add_nearest_neighbor_result(
    gdf: gpd.GeoDataFrame, 
    analysis_date: str,
    **kwargs
) -> pd.DataFrame:
    """
    Add the nearest vp_idx. Also add and trio of be the boundary
    of nearest_vp_idx. Trio provides the vp_idx, timestamp,
    and vp coords we need to do stop arrival interpolation.
    """
    # Grab vp_condensed, which contains all the coords for entire trip
    vp_full = gpd.read_parquet(
        f"{SEGMENT_GCS}condensed/vp_condensed_{analysis_date}.parquet",
        columns = ["trip_instance_key", "vp_idx", 
                   "location_timestamp_local", 
                   "geometry"],
        **kwargs
    ).rename(columns = {
        "vp_idx": "trip_vp_idx",
        "geometry": "trip_geometry"
    }).set_geometry("trip_geometry").to_crs(WGS84)
    
    gdf2 = pd.merge(
        gdf,
        vp_full,
        on = "trip_instance_key",
        how = "inner"
    )
        
    nearest_vp_idx_series = []    
    vp_trio_series = []
    time_trio_series = []
    coords_trio_series = []
    
    # Iterate through and find the nearest_vp_idx, then surrounding trio
    nearest_vp_idx = np.vectorize(add_nearest_vp_idx)( 
        gdf2.vp_geometry, gdf2.stop_geometry, gdf2.vp_idx
    )
        
    gdf2 = gdf2.assign(
        nearest_vp_idx = nearest_vp_idx,
    ).drop(
        columns = ["vp_idx", "vp_geometry"]
    )
    
    for row in gdf2.itertuples():
        vp_trio, time_trio, coords_trio = add_trio(
            getattr(row, "nearest_vp_idx"), 
            np.asarray(getattr(row, "trip_vp_idx")),
            np.asarray(getattr(row, "location_timestamp_local")),
            np.asarray(getattr(row, "trip_geometry").coords),
        )
        
        vp_trio_series.append(vp_trio)
        time_trio_series.append(time_trio)
        coords_trio_series.append(shapely.LineString(coords_trio))
                
    drop_cols = [
        "location_timestamp_local",
        "trip_vp_idx", "trip_geometry"
    ]
    
    gdf2 = gdf2.assign(
        vp_idx_trio = vp_trio_series,
        location_timestamp_local_trio = time_trio_series,
        vp_coords_trio = gpd.GeoSeries(coords_trio_series, crs = WGS84)
    ).drop(columns = drop_cols)
        
    return gdf2

def add_nearest_neighbor_result_array(
    gdf: gpd.GeoDataFrame, 
    analysis_date: str,
    **kwargs
) -> pd.DataFrame:
    """
    Add the nearest k_neighbors result.
    """
    N_NEAREST_POINTS = 10
    
    nearest_vp_arr_series = []
    
    for row in gdf.itertuples():
        vp_coords_line = getattr(row, "vp_geometry")
        stop_geometry = getattr(row, "stop_geometry")
        vp_idx_arr = getattr(row, "vp_idx")
        
        np_inds = nearest_snap(
            vp_coords_line, stop_geometry, N_NEAREST_POINTS
        )
        
        # nearest neighbor returns self.N 
        # if there are no nearest neighbor results found
        # if we want 10 nearest neighbors and 8th, 9th, 10th are all
        # the same result, the 8th will have a result, then 9th and 10th will
        # return the length of the array (which is out-of-bounds)
        
        np_inds2 = np_inds[np_inds < vp_idx_arr.size]
        
        nearest_vp_arr = vp_idx_arr[np_inds2]
        
        nearest_vp_arr_series.append(nearest_vp_arr)
    
    gdf2 = gdf.assign(
        nearest_vp_arr = nearest_vp_arr_series
    ).drop(columns = ["vp_idx", "vp_geometry"])
    
    return gdf2