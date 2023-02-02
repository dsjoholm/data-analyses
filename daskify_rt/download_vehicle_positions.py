"""
Download vehicle positions for a day.
"""
import os
os.environ["CALITP_BQ_MAX_BYTES"] = str(800_000_000_000)

import datetime
import geopandas as gpd
import pandas as pd
import sys

from calitp.tables import tbls
from loguru import logger
from siuba import *

#from shared_utils import rt_dates

#analysis_date = rt_dates.DATES["jan2023"]
analysis_date = "2023-01-18"
GCS_FILE_PATH = "gs://calitp-analytics-data/data-analyses/"
DASK_TEST = f"{GCS_FILE_PATH}dask_test/"


def determine_batches(rt_names: list) -> dict:
    #https://stackoverflow.com/questions/4843158/how-to-check-if-a-string-is-a-substring-of-items-in-a-list-of-strings
    large_operator_names = [
        "LA Metro Bus",
        "LA Metro Rail",
        "AC Transit", 
        "Muni"
    ]

    # If any of the large operator name substring is 
    # found in our list of names, grab those
    # be flexible bc "Vehicle Positions" and "VehiclePositions" present
    matching = [i for i in rt_names 
                if any(name in i for name in large_operator_names)]
    remaining = [i for i in rt_names if i not in matching]
    
    # For each of the large operators, they will run in query individually,
    # and batch up the remaining together
    # if there are 4 large operators, then enumerate gives us 0, 1, 2, 3. 
    # so final batch is the 4th
    batch_dict = {}
    last_i = len(matching)
    
    for i, name in enumerate(matching):
        batch_dict[i] = [name]
    
    batch_dict[last_i] = remaining
    
    return batch_dict


def download_vehicle_positions(
    date: str,
    operator_names: list
) -> pd.DataFrame:    
    
    df = (tbls.mart_gtfs.fct_vehicle_locations()
          >> filter(_.dt == date)
          >> filter(_._gtfs_dataset_name.isin(operator_names))
          >> select(_.gtfs_dataset_key, 
                    _.trip_id,
                    _.location_timestamp,
                    _.location)
              >> collect()
         )
    
    # query_sql, parsing by the hour timestamp BQ column confusing
    #https://www.yuichiotsuka.com/bigquery-timestamp-datetime/
    
    return df


if __name__ == "__main__":
    from dask.distributed import Client
    
    client = Client("dask-scheduler.dask.svc.cluster.local:8786")
    
    logger.add("./logs/download_vp_v2.log", 
               retention="3 months")
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

    rt_datasets.to_parquet("./data/rt_datasets.parquet")
    
    rt_datasets = pd.read_parquet("./data/rt_datasets.parquet")
    
    # Exclude regional feed and precursors
    exclude = ["Bay Area 511 Regional VehiclePositions"]
    rt_datasets = rt_datasets[
        ~(rt_datasets.name.isin(exclude)) & 
        (rt_datasets.regional_feed_type != "Regional Precursor Feed")
    ].reset_index(drop=True)
    
    rt_dataset_names = rt_datasets.name.unique().tolist()

    batches = determine_batches(rt_dataset_names)
    
    for i, subset_operators in batches.items():
        
        time0 = datetime.datetime.now()
        
        if i > 1:
            logger.info(f"batch {i}: {subset_operators}")
            df = download_vehicle_positions(
                analysis_date, subset_operators)

            df.to_parquet(
                f"{DASK_TEST}vp_raw_{analysis_date}_batch{i}.parquet")

            time1 = datetime.datetime.now()
            logger.info(f"exported batch {i} to GCS: {time1 - time0}")
    
    end = datetime.datetime.now()
    logger.info(f"execution time: {end - start}")
        
    client.close()