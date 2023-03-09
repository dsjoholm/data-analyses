"""
Download vehicle positions for a day.
"""
import os
os.environ["CALITP_BQ_MAX_BYTES"] = str(800_000_000_000)

import datetime
import gcsfs
import geopandas as gpd
import pandas as pd
import shapely
import sys

from calitp_data_analysis.tables import tbls
from loguru import logger
from siuba import *

from segment_speed_utils import helpers
from shared_utils import utils, gtfs_utils_v2
from update_vars import SEGMENT_GCS, analysis_date

fs = gcsfs.GCSFileSystem()

def determine_batches(rt_names: list) -> dict:
    #https://stackoverflow.com/questions/4843158/how-to-check-if-a-string-is-a-substring-of-items-in-a-list-of-strings
    large_operator_names = [
        "LA Metro Bus",
        "LA Metro Rail",
        "AC Transit", 
        "Muni"
    ]
    
    bay_area_names = [
        "Bay Area 511"
    ]

    # If any of the large operator name substring is 
    # found in our list of names, grab those
    # be flexible bc "Vehicle Positions" and "VehiclePositions" present
    matching = [i for i in rt_names 
                if any(name in i for name in large_operator_names)]
    
    remaining_bay_area = [i for i in rt_names 
                          if any(name in i for name in bay_area_names) and 
                          i not in matching
                         ]
    remaining = [i for i in rt_names if 
                 i not in matching and i not in remaining_bay_area]
    
    # Batch large operators together and run remaining in 2nd query
    batch_dict = {}
    
    batch_dict[0] = matching
    batch_dict[1] = remaining_bay_area
    batch_dict[2] = remaining
    
    return batch_dict


def download_vehicle_positions(
    date: str,
    operator_names: list
) -> pd.DataFrame:    
    
    df = (tbls.mart_gtfs.fct_vehicle_locations()
          >> filter(_.dt == date)
          >> filter(_._gtfs_dataset_name.isin(operator_names))
          >> select(_.gtfs_dataset_key, _._gtfs_dataset_name,
                    _.trip_id,
                    _.location_timestamp,
                    _.location)
              >> collect()
         )
    
    # query_sql, parsing by the hour timestamp BQ column confusing
    #https://www.yuichiotsuka.com/bigquery-timestamp-datetime/
    
    return df


def loop_through_batches_and_download_vp(
    batches: dict, 
    analysis_date: str
):
    """
    Loop through batches dictionary and download vehicle positions.
    Download for that batch of operators, for that date.
    """
    for i, subset_operators in batches.items():
        time0 = datetime.datetime.now()

        logger.info(f"batch {i}: {subset_operators}")
        df = download_vehicle_positions(
            analysis_date, subset_operators)

        df.to_parquet(
            f"{SEGMENT_GCS}vp_raw_{analysis_date}_batch{i}.parquet")
        
        time1 = datetime.datetime.now()
        logger.info(f"exported batch {i} to GCS: {time1 - time0}")
        
        
if __name__ == "__main__":
    from dask.distributed import Client
    
    client = Client("dask-scheduler.dask.svc.cluster.local:8786")
    
    LOG_FILE = "../logs/download_vp_v2.log"
    logger.add(LOG_FILE, retention="3 months")
    logger.add(sys.stderr, 
               format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}", 
               level="INFO")
    
    logger.info(f"Analysis date: {analysis_date}")
    
    start = datetime.datetime.now()
    
    # Get rt_datasets that are available for that day
    rt_datasets = gtfs_utils_v2.get_transit_organizations_gtfs_dataset_keys(
        keep_cols=["key", "name", "type", "regional_feed_type"],
        custom_filtering={"type": ["vehicle_positions"]},
        get_df = True
    ) >> collect()
    
    
    # Exclude regional feed and precursors
    exclude = ["Bay Area 511 Regional VehiclePositions"]
    rt_datasets = rt_datasets[
        ~(rt_datasets.name.isin(exclude)) & 
        (rt_datasets.regional_feed_type != "Regional Precursor Feed")
    ].reset_index(drop=True)
    
    rt_dataset_names = rt_datasets.name.unique().tolist()
    batches = determine_batches(rt_dataset_names)
    
    one_day_after = helpers.find_day_after(analysis_date)
    
    # Loop through batches and download the date we're interested in 
    # and the day after
    loop_through_batches_and_download_vp(batches, analysis_date)
    #loop_through_batches_and_download_vp(batches, one_day_after)
        
    end = datetime.datetime.now()
    logger.info(f"execution time: {end - start}")
        
    client.close()