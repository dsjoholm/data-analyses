"""
General utility functions.
"""
import base64
import os
import shutil
from pathlib import Path
from typing import Union

import fsspec
import geopandas as gpd
import requests
from calitp.storage import get_fs

fs = get_fs()


def geoparquet_gcs_export(gdf: gpd.GeoDataFrame, gcs_file_path: str, file_name: str):
    """
    Save geodataframe as parquet locally,
    then move to GCS bucket and delete local file.

    gdf: geopandas.GeoDataFrame
    gcs_file_path: str
                    Ex: gs://calitp-analytics-data/data-analyses/my-folder/
    file_name: str
                Filename, with or without .parquet.
    """
    file_name_sanitized = file_name.replace(".parquet", "")
    gdf.to_parquet(f"./{file_name_sanitized}.parquet")
    fs.put(
        f"./{file_name_sanitized}.parquet",
        f"{gcs_file_path}{file_name_sanitized}.parquet",
    )
    os.remove(f"./{file_name_sanitized}.parquet")


def download_geoparquet(
    gcs_file_path: str, file_name: str, save_locally: bool = False
) -> gpd.GeoDataFrame:
    """
    Parameters:
    gcs_file_path: str
                    Ex: gs://calitp-analytics-data/data-analyses/my-folder/
    file_name: str
                name of file (with or without the .parquet).
    save_locally: bool
                    defaults to False. if True, will save geoparquet locally.
    """
    file_name_sanitized = file_name.replace(".parquet", "")

    object_path = fs.open(f"{gcs_file_path}{file_name_sanitized}.parquet")
    gdf = gpd.read_parquet(object_path)

    if save_locally is True:
        gdf.to_parquet(f"./{file_name}.parquet")

    return gdf


def geojson_gcs_export(
    gdf: gpd.GeoDataFrame,
    gcs_file_path: str,
    file_name: str,
    geojson_type: str = "geojson",
):
    """
    Save geodataframe as geojson locally,
    then move to GCS bucket and delete local file.

    gcs_file_path: str
                    Ex: gs://calitp-analytics-data/data-analyses/my-folder/
    file_name: str
                name of file (with .geojson or .geojsonl).
    """

    if geojson_type == "geojson":
        DRIVER = "GeoJSON"
    elif geojson_type == "geojsonl":
        DRIVER = "GeoJSONSeq"
    else:
        raise ValueError("Not a valid geojson type! Use `geojson` or `geojsonl`")

    file_name_sanitized = file_name.replace(f".{geojson_type}", "")

    gdf.to_file(f"./{file_name_sanitized}.{geojson_type}", driver=DRIVER)

    fs.put(
        f"./{file_name_sanitized}.{geojson_type}",
        f"{gcs_file_path}{file_name_sanitized}.{geojson_type}",
    )
    os.remove(f"./{file_name_sanitized}.{geojson_type}")


# Make zipped shapefile
# https://github.com/CityOfLosAngeles/planning-entitlements/blob/master/notebooks/utils.py
def make_shapefile(gdf: gpd.GeoDataFrame, path: Union[str, Path]) -> tuple[Path, str]:
    """
    Make a zipped shapefile and save locally
    Parameters
    ==========
    gdf: gpd.GeoDataFrame to be saved as zipped shapefile
    path: str, local path to where the zipped shapefile is saved.
            Ex: "folder_name/census_tracts"
                "folder_name/census_tracts.zip"

    Remember: ESRI only takes 10 character column names!!

    Returns a folder name (dirname) where the shapefile is stored and
    a filename. Both are strings.
    """
    # Grab first element of path (can input filename.zip or filename)
    dirname = os.path.splitext(path)[0]
    print(f"Path name: {path}")
    print(f"Dirname (1st element of path): {dirname}")

    # Make sure there's no folder with the same name
    shutil.rmtree(dirname, ignore_errors=True)

    # Make folder
    os.mkdir(dirname)
    shapefile_name = f"{os.path.basename(dirname)}.shp"
    print(f"Shapefile name: {shapefile_name}")

    # Export shapefile into its own folder with the same name
    gdf.to_file(driver="ESRI Shapefile", filename=f"{dirname}/{shapefile_name}")
    print(f"Shapefile component parts folder: {dirname}/{shapefile_name}")

    return dirname, shapefile_name


def make_zipped_shapefile(gdf: gpd.GeoDataFrame, path: Union[str, Path]):
    """
    Make a zipped shapefile and save locally
    Parameters
    ==========
    gdf: gpd.GeoDataFrame to be saved as zipped shapefile
    path: str, local path to where the zipped shapefile is saved.
            Ex: "folder_name/census_tracts"
                "folder_name/census_tracts.zip"

    Remember: ESRI only takes 10 character column names!!
    """
    dirname, shapefile_name = make_shapefile(gdf, path)

    # Zip it up
    shutil.make_archive(dirname, "zip", dirname)
    # Remove the unzipped folder
    shutil.rmtree(dirname, ignore_errors=True)


# Function to overwrite file in GitHub
# Based on https://github.com/CityOfLosAngeles/aqueduct/tree/master/civis-aqueduct-utils/civis_aqueduct_utils

DEFAULT_COMMITTER = {
    "name": "Service User",
    "email": "my-email@email.com",
}


def upload_file_to_github(
    token: str,
    repo: str,
    branch: str,
    path: str,
    local_file_path: str,
    commit_message: str,
    committer: dict = DEFAULT_COMMITTER,
):
    """
    Parameters
    ----------
    token: str
        GitHub personal access token and corresponds to GITHUB_TOKEN
        in Civis credentials.
    repo: str
        Repo name, such as 'CityofLosAngeles/covid19-indicators`
    branch: str
        Branch name, such as 'master'
    path: str
        Path to the file within the repo.
    local_file_path: str
        Path to the local file to be uploaded to the repo, which can differ
        from the path within the GitHub repo.
    commit_message: str
        Commit message used when making the git commit.
    commiter: dict
        name and email associated with the committer.
    """

    BASE = "https://api.github.com"

    # Get the sha of the previous version.
    # Operate on the dirname rather than the path itself so we
    # don't run into file size limitations.
    r = requests.get(
        f"{BASE}/repos/{repo}/contents/{os.path.dirname(path)}",
        params={"ref": branch},
        headers={"Authorization": f"token {token}"},
    )
    r.raise_for_status()
    item = next(i for i in r.json() if i["path"] == path)
    sha = item["sha"]

    # Upload the new version
    with fsspec.open(local_file_path, "rb") as f:
        contents = f.read()

    r = requests.put(
        f"{BASE}/repos/{repo}/contents/{path}",
        headers={"Authorization": f"token {token}"},
        json={
            "message": commit_message,
            "committer": committer,
            "branch": branch,
            "sha": sha,
            "content": base64.b64encode(contents).decode("utf-8"),
        },
    )
    r.raise_for_status()
