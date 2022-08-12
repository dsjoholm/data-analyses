"""
Take single operator HQTA and combine across operators.

Additional data cleaning to filter out small HQTA segments.

This takes 2 min to run. 
"""
import dask.dataframe as dd
import dask_geopandas
import datetime as dt
import geopandas as gpd

import operators_for_hqta
from shared_utils import utils
from utilities import GCS_FILE_PATH
from update_vars import VALID_OPERATORS_FILE

# Read first one in, to set the metadata for dask gdf
OPERATOR_PATH = f"{GCS_FILE_PATH}bus_corridors/"

ITP_IDS_IN_GCS = operators_for_hqta.itp_ids_from_json(file=VALID_OPERATORS_FILE)
first_operator = ITP_IDS_IN_GCS[0]

if __name__ == "__main__":
    start = dt.datetime.now()
    
    # Read in first operator to set the metadata for dask gdf
    gdf = dask_geopandas.read_parquet(
        f'{OPERATOR_PATH}{first_operator}_bus.parquet'
    )

    for itp_id in ITP_IDS_IN_GCS[1:]:
        operator = dask_geopandas.read_parquet(
            f'{OPERATOR_PATH}{itp_id}_bus.parquet')

        gdf = dd.multi.concat([gdf, operator], axis=0)
    
    print("Concatenated all operators")
    
    # Compute to make it a gdf
    gdf2 = gdf.compute().reset_index(drop=True)
    
    utils.geoparquet_gcs_export(gdf2, 
                                f'{GCS_FILE_PATH}intermediate/', 
                                'all_bus')
    
    end = dt.datetime.now()
    print(f"Execution time: {end-start}")