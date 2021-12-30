"""
Functions to create routes and stops dataset 
for AGOL.

Query gtfs_schedule tables, assemble,
export as geoparquet in GCS, and 
export as zipped shapefile or geojson
"""
import geopandas as gpd

from datetime import datetime

import prep_data
import create_routes_data
import create_stops_data
from shared_utils import utils


def create_shapefiles_and_export():
    time0 = datetime.now()
    
    # Create local parquets
    prep_data.create_local_parquets() 
    print("Local parquets created")
    
    routes = create_routes_data.make_routes_shapefile()    
    stops = create_stops_data.make_stops_shapefile()
            
    # Export geoparquets to GCS
    utils.geoparquet_gcs_export(routes, prep_data.GCS_FILE_PATH, "routes_assembled")
    utils.geoparquet_gcs_export(stops, prep_data.GCS_FILE_PATH, "stops_assembled")
    
    print("Geoparquets exported to GCS")
        
    # To read geoparquets in without putting it in catalog
    #routes = utils.download_geoparquet(prep_data.GCS_FILE_PATH, "routes_assembled", save_locally=True)
    #stops = utils.download_geoparquet(prep_data.GCS_FILE_PATH, "stops_assembled", save_locally=True)
        
    # Export as zipped shapefile (10-char column names)
    utils.make_zipped_shapefile(routes, "routes_assembled.zip")
    utils.make_zipped_shapefile(stops, "stops_assembled.zip")
    
    # Delete local parquets
    #prep_data.delete_local_parquets()
    print("Local parquets deleted")
    
    time1 = datetime.now()
    print(f"Total run time for routes/stops script: {time1-time0}")
    
    
create_shapefiles_and_export()