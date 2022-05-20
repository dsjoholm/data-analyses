"""
Geocode addresses.

Cache results as JSON in GCS.
Compile and add to dataframe.
"""
import geocoder
import os
import pandas as pd
import pickle

import utils


def geocode_address(row):
    input_address = row.full_address
    
    g = geocoder.osm(input_address)
    # results are a dict with x, y, address components
    # keep it all, since we don't always have zip_code
    # also use this as sanity check
    results = g.osm
    
    utils.save_request_json(results, row.sheet_uuid, 
                            DATA_PATH = utils.DATA_PATH, 
                            GCS_FILE_PATH = f"{utils.GCS_FILE_PATH}geocode_cache/")
    
    print(f"Cached {row.sheet_uuid}")
    
    return row.sheet_uuid
    

# Parse the results dict and compile as pd.Series
def compile_results(results):
    longitude = results["x"]
    latitude = results["y"]
    house_number = results["addr:housenumber"]
    street = results["addr:street"]
    city = results["addr:state"]
    state = results["addr:state"]
    country = results["addr:country"]
    postal = results["addr:postal"]

    return pd.Series(
        [longitude, latitude, 
         house_number, street,
         city, state, country, postal], 
        index= ["longitude", "latitude", 
                "house_number", "street",
                "city", "state", "country", "postal"]
    )


if __name__ == "__main__":
    df = pd.read_parquet(f"{utils.GCS_FILE_PATH}for_geocoding.parquet")
    
    # Now that we removed the stuff in parentheses, 
    # the same location comes up multiple times
    # just throw 1 into geocoder, merge it back in to full df later
    keep_cols = ["full_address", "city", "zip_code", "sheet_uuid"]

    # Keep sheet_uuid to cache json results and have an identifier for the name
    # but don't use it to merge it back in
    geocode_df = df[keep_cols].drop_duplicates(
        subset=["full_address", "city", "zip_code"])
    
    
    # Geocode and cache results
    # Assume it's going to take batches to compile
    
    # https://stackoverflow.com/questions/26835477/pickle-load-variable-if-exists-or-create-and-save-it
    # If pickle file is found, use it. Otherwise, create any empty pickle file
    # to hold uuids that have cached results
    def read_or_new_pickle(path, default_in_file):
        if os.path.isfile(path):
            with open(path, "rb") as f:
                try:
                    return pickle.load(f)
                except Exception: # so many things could go wrong, can't be more specific.
                    pass 
        with open(path, "wb") as f:
            pickle.dump(default_in_file, f)
        return default_in_file
    
    # Returns empty list the first time
    # after, should return list with results
    have_results = read_or_new_pickle(f"{utils.DATA_PATH}cached_results_uuid.pickle", [])
    
    unique_uuid = list(geocode_df.sheet_uuid)
    
    no_results_yet = set(unique_uuid).difference(set(have_results))
    
    for i in no_results_yet:
        result_uuid = geocode_df[geocode_df.sheet_uuid == i].apply(
            lambda x: geocode_address(x), axis=1)