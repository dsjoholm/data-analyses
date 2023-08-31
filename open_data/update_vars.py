from shared_utils import rt_dates

analysis_date = rt_dates.DATES["apr2023b"]

GCS_FILE_PATH = "gs://calitp-analytics-data/data-analyses/"
COMPILED_CACHED_VIEWS = f"{GCS_FILE_PATH}rt_delay/compiled_cached_views/"
TRAFFIC_OPS_GCS = f"{GCS_FILE_PATH}traffic_ops/"
HQTA_GCS = f"{GCS_FILE_PATH}high_quality_transit_areas/"
SEGMENT_GCS = f"{GCS_FILE_PATH}rt_segment_speeds/"

ESRI_BASE_URL = "https://gisdata.dot.ca.gov/arcgis/rest/services/CHrailroad/"
DEFAULT_XML_TEMPLATE = "default_pro.xml"