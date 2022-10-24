"""
Do clipping to find where bus corridors intersect.

With hqta_segment_id clipping, but looping across route_id, 
it takes 42 min to run.
LA Metro takes 3.5 min to run.

With route_id clipping, takes 1 hr 52 min to run: 
LA Metro takes 6 min to run, and ITP ID 4 takes 4 min to run.
Big Blue Bus takes 10 min to run.

From combine_and_visualize.ipynb
"""
import dask.dataframe as dd
import dask_geopandas as dg
import datetime as dt
import geopandas as gpd
import glob
import os
import pandas as pd
import sys

from loguru import logger

#import C1_prep_for_clipping as prep_clip
import C1_new as prep_clip
from shared_utils import utils
#from utilities import catalog_filepath, GCS_FILE_PATH
from update_vars import analysis_date

logger.add("./logs/C2_new.log")
logger.add(sys.stderr, 
           format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}", 
           level="INFO")

segment_cols = ["calitp_itp_id", "hqta_segment_id"]

intersect_segment_cols = ["intersect_calitp_itp_id", "intersect_hqta_segment_id"]

# Input files
#PAIRWISE_FILE = catalog_filepath("pairwise_intersections")
#SUBSET_CORRIDORS = catalog_filepath("subset_corridors")
DASK_GCS = "gs://calitp-analytics-data/data-analyses/dask_test/"
GCS_FILE_PATH = DASK_GCS

PAIRWISE_FILE = f"{DASK_GCS}intermediate/pairwise.parquet"
SUBSET_CORRIDORS = f"{DASK_GCS}intermediate/subset_corridors.parquet"

def get_operator_intersections_as_clipping_mask(
    corridors_df: dg.GeoDataFrame, intersecting_pairs: dd.DataFrame, 
    itp_id: int) -> gpd.GeoDataFrame:
    """
    For an operator, look in the pairwise table and find the intersections.
    Attach the line geom back on, which is needed for clipping.
    
    Return a gpd.GeoDataFrame 
    The clipping mask can be gpd.GeoDataFrame, cannot be dg.GeoDataFrame
    """
    intersecting_pairs = (intersecting_pairs[
        intersecting_pairs.calitp_itp_id == itp_id]
        [intersect_segment_cols]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    
    # Rename columns so it's not intersect_
    operator_pairs = prep_clip.rename_cols(intersecting_pairs, with_intersect=False)
    
    # Merge back into dask gdf to get geom
    # Can't use isin with dask
    operator_pairs_with_geom = dd.merge(
        corridors_df,
        operator_pairs,
        on = segment_cols,
        how = "inner",
    )
    
    # Run compute() because masking df has to be gdf
    return operator_pairs_with_geom.compute()
    
    
def clip_by_itp_id(corridors_df: dg.GeoDataFrame, 
                   intersecting_pairs: dd.DataFrame, 
                   itp_id: int) -> dg.GeoDataFrame:
    """
    Do the clipping for each operator.
    Loop through by route_id (more aggregated than hqta_segments, but not as
    aggregated as entire operator, which could be really slow to do the clipping).
    """
    start = dt.datetime.now()
    
    operator = corridors_df[corridors_df.calitp_itp_id == itp_id]
    
    corresponding_pairs = get_operator_intersections_as_clipping_mask(
        corridors_df, intersecting_pairs, itp_id)
    
    # These are the possible segments that should be used as the masking df in the clip
    # Do it at the operator-level
    # Since 1 segment is selected in the loop, it doesn't matter if the masking df is large    
    operator_segments = list(operator.route_id.unique())
    
    # Set the dask metadata
    intersections = operator.head(0)
    
    for i in operator_segments:
        clipped_segment = dg.clip(
            operator[operator.route_id == i],
            corresponding_pairs[corresponding_pairs.route_id != i], 
            keep_geom_type = True
        )
        
        intersections = dd.multi.concat([intersections, 
                                         clipped_segment], axis=0)
                            
    end = dt.datetime.now()
    logger.info(f"clipping for {itp_id}: {end-start}")
    
    return intersections


def delete_local_clipped_files():
    temp_operator_files = [f for f in glob.glob("./data/intersections/clipped_*.parquet")]
    
    for f in temp_operator_files:
        os.remove(f)
    

if __name__ == "__main__":
    logger.info(f"Analysis date: {analysis_date}")

    start = dt.datetime.now()
        
    intersecting_pairs = dd.read_parquet(PAIRWISE_FILE)
    corridors = dg.read_parquet(SUBSET_CORRIDORS)
    
    # Use the subsetted down list of ITP IDS
    VALID_ITP_IDS = list(corridors.calitp_itp_id.unique())
    
    time1 = dt.datetime.now()
    logger.info(f"read in data, assemble valid ITP_IDS: {time1 - start}")
    
    clipped = corridors.head(0)

    for itp_id in sorted(VALID_ITP_IDS):
        intersection = clip_by_itp_id(corridors, intersecting_pairs, itp_id)
        
        # If there are no clips, then skip the concatenation
        if len(intersection.index) > 0:
            intersection2 = intersection.compute()
            intersection2.to_parquet(f"./data/intersections/clipped_{itp_id}.parquet")
            
            clipped = dd.multi.concat([clipped, intersection], axis=0)
        else:
            continue
    
    
    clipped2 = (clipped.compute()
                .sort_values(segment_cols, ascending=[True, True])
                .reset_index(drop=True)
               )
    
    time2 = dt.datetime.now()
    logger.info(f"compute for full clipped df: {time2 - time1}")
    
    utils.geoparquet_gcs_export(clipped2,
                                GCS_FILE_PATH,
                                'all_clipped')    
    
    # Delete the temporary clipped files for each operator
    delete_local_clipped_files()
    
    end = dt.datetime.now()
    logger.info(f"execution time: {end-start}")