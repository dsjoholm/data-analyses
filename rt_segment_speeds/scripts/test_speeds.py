import os
os.environ['USE_PYGEOS'] = '0'

import dask.dataframe as dd
import dask_geopandas as dg
import datetime
import geopandas as gpd
import numpy as np
import pandas as pd
import sys

from loguru import logger

from shared_utils import geography_utils
from shared_utils.rt_utils import MPH_PER_MPS
from segment_speed_utils import helpers, segment_calcs, wrangle_shapes
from segment_speed_utils.project_vars import (SEGMENT_GCS, analysis_date, 
                                              PROJECT_CRS, CONFIG_PATH)   

def get_usable_vp_bounds_by_trip(df: dd.DataFrame) -> pd.DataFrame:
    """
    Of all the usable vp, for each trip, find the min(vp_idx)
    and max(vp_idx).
    For the first stop, there will never be a previous vp to find,
    because the previous vp_idx will belong to a different operator/trip.
    But for segments in the middle of the shape, the previous vp can be anywhere,
    maybe several segments away.
    """
    
    grouped_df = df.groupby("trip_instance_key", 
                            observed=True, group_keys=False)

    start_vp = (grouped_df.vp_idx.min().reset_index()
                .rename(columns = {"vp_idx": "min_vp_idx"})
               )
    end_vp = (grouped_df.vp_idx.max().reset_index()
              .rename(columns = {"vp_idx": "max_vp_idx"})
             )
    
    df2 = dd.merge(
        start_vp,
        end_vp,
        on = "trip_instance_key",
        how = "left"
    ).reset_index(drop=True).compute()
    
    return df2

def linear_referencing_vp_against_line(
    vp: dd.DataFrame, 
    segments: gpd.GeoDataFrame,
    segment_identifier_cols: list,
    timestamp_col: str
) -> dd.DataFrame:
    time0 = datetime.datetime.now()
    
    # https://stackoverflow.com/questions/71685387/faster-methods-to-create-geodataframe-from-a-dask-or-pandas-dataframe
    # https://github.com/geopandas/dask-geopandas/issues/197    
    vp_gddf = dg.from_dask_dataframe(
        vp, 
        geometry=dg.points_from_xy(vp, "x", "y")
    ).set_crs(geography_utils.WGS84).to_crs(PROJECT_CRS).drop(columns = ["x", "y"])
    
    vp_with_seg_geom = dd.merge(
        vp_gddf, 
        segments,
        on = segment_identifier_cols,
        how = "inner"
    ).rename(columns = {
        "geometry_x": "vp_geometry",
        "geometry_y": "segment_geometry"}
    ).set_geometry("vp_geometry")

    vp_with_seg_geom = vp_with_seg_geom.repartition(npartitions=50)
          
    time1 = datetime.datetime.now()
    logger.info(f"set up merged vp with segments: {time1 - time0}")
    
    shape_meters_series = vp_with_seg_geom.map_partitions(
        wrangle_shapes.project_point_geom_onto_linestring,
        "segment_geometry",
        "vp_geometry",
        meta = ("shape_meters", "float")
    )
    
    vp_with_seg_geom = segment_calcs.convert_timestamp_to_seconds(
        vp_with_seg_geom, [timestamp_col])
    
    vp_with_seg_geom = vp_with_seg_geom.assign(
        shape_meters = shape_meters_series,
        segment_meters = vp_with_seg_geom.segment_geometry.length
    )
    
    time2 = datetime.datetime.now()
    logger.info(f"linear referencing: {time2 - time1}")
    
    drop_cols = [f"{timestamp_col}", "vp_geometry", "segment_geometry"]
    vp_with_seg_geom2 = vp_with_seg_geom.drop(columns = drop_cols)
    
    return vp_with_seg_geom2
    

def make_wide(
    df: dd.DataFrame, 
    group_cols: list,
    timestamp_col: str
) -> dd.DataFrame:
    """
    Get df wide and set up current vp_idx and get meters/sec_elapsed
    against prior.
    """
    vp2 = (
        df.groupby(group_cols, 
                   observed=True, group_keys=False)
        .agg({"vp_idx": "max"})
        .reset_index()
        .merge(
            df,
            on = group_cols + ["vp_idx"],
            how = "inner"
        )
    )

    vp1 = (
        df.groupby(group_cols, 
                   observed=True, group_keys=False)
        .agg({"vp_idx": "min"})
        .reset_index()
        .merge(
            df,
            on = group_cols + ["vp_idx"],
            how = "inner"
        ).rename(columns = {
            "vp_idx": "prior_vp_idx",
            f"{timestamp_col}_sec": f"prior_{timestamp_col}_sec",
            "shape_meters": "prior_shape_meters",
        })
    )
    
    df_wide = dd.merge(
        vp2,
        vp1,
        on = group_cols,
        how = "left"
    )
    
    df_wide = df_wide.assign(
        meters_elapsed = (df_wide.shape_meters - 
                          df_wide.prior_shape_meters).abs(),
        sec_elapsed = (df_wide[f"{timestamp_col}_sec"]- 
                       df_wide[f"prior_{timestamp_col}_sec"]).abs(),
    )
    
    df_wide = df_wide.assign(
        pct_segment = df_wide.meters_elapsed.divide(df_wide.segment_meters)
    )
    
    return df_wide
    

def calculate_speed(
    df: dd.DataFrame, 
    distance_cols: tuple = ("prior_shape_meters", "shape_meters"), 
    time_cols: tuple = ("prior_location_timestamp_local_sec", "location_timestamp_local_sec")
) -> dd.DataFrame:
    
    min_dist, max_dist = distance_cols
    min_time, max_time = time_cols
    
    df = df.assign(
        meters_elapsed = (df[max_dist] - df[min_dist]).abs(),
        sec_elapsed = (df[max_time] - df[min_time]).abs(),
    )
    
    df = df.assign(
        speed_mph = (df.meters_elapsed.divide(df.sec_elapsed) * 
                 MPH_PER_MPS)
    )
    
    return df
    
       
def filter_for_unstable_speeds(
    df: pd.DataFrame,
    pct_segment_threshold: float
) -> tuple[pd.DataFrame]:
    ok_speeds = df[df.pct_segment > pct_segment_threshold]
    low_speeds = df[df.pct_segment <= pct_segment_threshold]
    
    return ok_speeds, low_speeds

def low_speed_segments_select_different_prior_vp(
    low_speeds_df: pd.DataFrame,
    group_cols: list,
    timestamp_col: str
):

    keep_cols = group_cols + [
        "vp_idx", "location_timestamp_local_sec",
    ]
    
    df1 = low_speeds_df[keep_cols]
    
    df1 = df1.assign(
        prior_vp_idx = df1.vp_idx -1 
    )
    
    usable_vp = dd.read_parquet(
        f"{SEGMENT_GCS}vp_usable_{analysis_date}",
        columns = ["trip_instance_key", "vp_idx", timestamp_col, "x", "y"]
    )

    vp_idx_bounds = get_usable_vp_bounds_by_trip(usable_vp)
    
    df2 = pd.merge(
        df1, 
        vp_idx_bounds,
        on = "trip_instance_key",
        how = "inner"
    )
    
    df2 = df2.assign(
        prior_vp_idx = df2.apply(
            lambda x: 
            x.vp_idx + 1 if (x.prior_vp_idx < x.min_vp_idx) and 
            (x.vp_idx + 1 <= x.max_vp_idx)
            else x.prior_vp_idx, 
            axis=1)
    ).drop(columns = ["trip_instance_key", "min_vp_idx", "max_vp_idx"])
    

    subset_vp_idx = np.union1d(
        df2.vp_idx.unique(), 
        df2.prior_vp_idx.unique()
    ).tolist()
    
    usable_vp2 = usable_vp[usable_vp.vp_idx.isin(subset_vp_idx)].compute()
    
    usable_gdf = geography_utils.create_point_geometry(
        usable_vp2,
        longitude_col = "x",
        latitude_col = "y",
        crs = PROJECT_CRS
    ).drop(columns = ["x", "y"]).reset_index(drop=True)
    
    usable_gdf2 = segment_calcs.convert_timestamp_to_seconds(
        usable_gdf, [timestamp_col]).drop(columns = timestamp_col)
    
    # Merge in coord for current_vp_idx
    # we already have a timestamp_sec for current vp_idx
    gdf = pd.merge(
        usable_gdf2.drop(columns = f"{timestamp_col}_sec"),
        df2,
        on = "vp_idx",
        how = "inner"
    )
    
    # Merge in coord for prior_vp_idx
    gdf2 = pd.merge(
        gdf,
        usable_gdf2[["vp_idx", f"{timestamp_col}_sec", "geometry"]].add_prefix("prior_"),
        on = "prior_vp_idx",
        how = "inner"
    )
    
    # should we do straight distance or interpolate against full shape?
    # what if full shape is problematic?
    # do we want to do a check against the scale? that's not very robust either though

    gdf2 = gdf2.assign(
        straight_distance = gdf2.geometry.distance(gdf2.prior_geometry)
    )
    
    gdf2 = gdf2.assign(
        sec_elapsed = (gdf2[f"{timestamp_col}_sec"] - 
                   gdf2[f"prior_{timestamp_col}_sec"]).abs()
    )
    
    gdf2 = gdf2.assign(
        speed_mph = gdf2.straight_distance.divide(gdf2.sec_elapsed) * MPH_PER_MPS
    )
    
    drop_cols = ["geometry", "prior_geometry"]
    results = gdf2.drop(columns = drop_cols)
                        
    return results


def linear_referencing_and_speed_by_segment(
    analysis_date: str,
    dict_inputs: dict = {}
):
    """
    With just enter / exit points on segments, 
    do the linear referencing to get shape_meters, and then derive speed.
    """
    time0 = datetime.datetime.now()    
    
    VP_FILE = dict_inputs["stage3"]
    SEGMENT_FILE = dict_inputs["segments_file"]
    SEGMENT_IDENTIFIER_COLS = dict_inputs["segment_identifier_cols"]
    TIMESTAMP_COL = dict_inputs["timestamp_col"]    
    EXPORT_FILE = dict_inputs["stage4"]
    
    # Keep subset of columns - don't need it all. we can get the 
    # columns dropped through segments file
    vp_keep_cols = [
        'trip_instance_key',
        TIMESTAMP_COL,
        'x', 'y', 'vp_idx'
    ] + SEGMENT_IDENTIFIER_COLS
    
    vp = dd.read_parquet(
        f"{SEGMENT_GCS}vp_pare_down/{VP_FILE}_all_{analysis_date}",
        columns = vp_keep_cols
    )
    
    segments = helpers.import_segments(
        SEGMENT_GCS,
        f"{SEGMENT_FILE}_{analysis_date}", 
        columns = SEGMENT_IDENTIFIER_COLS + ["geometry"]
    ).dropna(subset="geometry").reset_index(drop=True)
     
    vp_with_seg_geom = linear_referencing_vp_against_line(
        vp,
        segments,
        SEGMENT_IDENTIFIER_COLS,
        TIMESTAMP_COL
    ).persist()

    time1 = datetime.datetime.now()
    logger.info(f"linear referencing: {time1 - time0}")
    
    SEGMENT_TRIP_COLS = ["trip_instance_key", 
                         "segment_meters"] + SEGMENT_IDENTIFIER_COLS

    vp_with_seg_wide = make_wide(
        vp_with_seg_geom, SEGMENT_TRIP_COLS, TIMESTAMP_COL
    )
    
    initial_speeds = calculate_speed(
        vp_with_seg_wide, 
        distance_cols = ("prior_shape_meters", "shape_meters"),
        time_cols = (f"prior_{TIMESTAMP_COL}_sec", f"{TIMESTAMP_COL}_sec")
    ).compute()
    
    time2 = datetime.datetime.now()
    logger.info(f"make wide and get initial speeds: {time2 - time1}")
    
    ok_speeds, low_speeds = filter_for_unstable_speeds(
        initial_speeds,
        pct_segment_threshold = 0.3
    )
    
    low_speeds_recalculated = low_speed_segments_select_different_prior_vp(
        low_speeds,
        SEGMENT_TRIP_COLS,
        TIMESTAMP_COL
    )
    
    low_speeds_recalculated = low_speeds_recalculated.assign(
        flag_recalculated = 1,
        meters_elapsed = low_speeds_recalculated.straight_distance
    )
        
    keep_cols = SEGMENT_TRIP_COLS + [
        "vp_idx", "prior_vp_idx", 
        f"{TIMESTAMP_COL}_sec", f"prior_{TIMESTAMP_COL}_sec",
        "meters_elapsed",
        "sec_elapsed",
        "pct_segment",
        "speed_mph",
        "flag_recalculated",
    ]
    
    speeds = pd.concat([
        ok_speeds,
        low_speeds_recalculated
    ], axis=0).sort_values(SEGMENT_IDENTIFIER_COLS + ["trip_instance_key"]
                      ).reset_index(drop=True)    
    
    speeds = speeds.assign(
        flag_recalculated = speeds.flag_recalculated.fillna(0).astype("int8")
    )[keep_cols]
    
    time3 = datetime.datetime.now()
    logger.info(f"recalculate speeds and get final: {time3 - time2}")
    
    speeds.to_parquet(
        f"{SEGMENT_GCS}{EXPORT_FILE}_{analysis_date}_df.parquet", 
    )
    
    time4 = datetime.datetime.now()
    logger.info(f"execution time: {time4 - time0}")
    
if __name__ == "__main__":
    
    STOP_SEG_DICT = helpers.get_parameters(CONFIG_PATH, "stop_segments")
    
    linear_referencing_and_speed_by_segment(analysis_date, STOP_SEG_DICT)