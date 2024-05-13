import datetime
import geopandas as gpd
import pandas as pd
import shapely
import sys

from loguru import logger

from segment_speed_utils import helpers
from update_vars import SEGMENT_GCS, GTFS_DATA_DICT
from calitp_data_analysis import utils, geography_utils


def cut_longer_segments(
    stop_segments: gpd.GeoDataFrame, 
    segment_length: int
) -> gpd.GeoDataFrame:
    """
    For longer segments (longer than 1,000 meters), put it through
    segmentizing again and cut it into 1,000 meters or less.
    
    Add stop_sequence1 that is a float and is proportional
    distance along segment.
    Adjust segment_id so that the suffix increases for the
    segment components between 2 stops.
    """
    gdf = stop_segments.loc[stop_segments.segment_length > segment_length]
    
    gdf["segment_geometry"] = gdf.apply(
        lambda x:
        geography_utils.create_segments(x.geometry, int(segment_length)),
        axis=1
    )
    
    gdf2 = geography_utils.explode_segments(
        gdf,
        group_cols = ['trip_instance_key'],
        segment_col = 'segment_geometry'
    )
    
    trip_stop_cols = ["trip_instance_key", "stop_sequence"]

    gdf2 = gdf2.assign(
        segment_sequence2 = gdf2.groupby(trip_stop_cols).cumcount()
    )
    
    # Amend segment_id which has suffix "-1"
    # after we explode, the suffix needs to increase, -1, -2, -3
    gdf2 = gdf2.assign(
        # split off the last hyphen and add new suffix (segment_sequence)
        segment_id = (gdf2.segment_id
                      .str.rsplit('-1', n=1, expand=True)[0] +
                      "-" + gdf2.segment_sequence2.astype(str)                
                     )
    )
    
    # TODO: this might be unnecessarily complicated
    # leave for now, but maybe we can get away with just segment_sequence2
    # although for aggregation, we want to ensure segments have same endpoints
    # if we want to stack it, and maybe segment_sequence2 isn't sufficient?
    # we don't want to stack segment1 with segment1 
    
    # To get a new stop_sequence that is numeric, 
    # would have to calculate cumulative distance in the segment now
    gdf2["seg_length"] = gdf2.geometry.length
    gdf2["prev_seg_length"] = (gdf2.groupby(trip_stop_cols)
                               .seg_length
                               .shift(1)
                              )
    
    gdf2["seg_cumulative"] = (gdf2.groupby(trip_stop_cols)
                              .prev_seg_length
                              .cumsum()
                             )
    
    gdf2["seg_pct"] = gdf2.seg_cumulative.divide(
        gdf2.segment_length).round(2)
    
    keep_cols = stop_segments.columns.tolist()
    
    gdf3 = gdf2.assign(
        stop_sequence1 = (gdf2.stop_sequence + gdf2.seg_pct).fillna(
            gdf2.stop_sequence)
    )[keep_cols + ["stop_sequence1"]] 

    return gdf3


def get_proxy_stops(
    longer_segments: gpd.GeoDataFrame,
    analysis_date: str
) -> gpd.GeoDataFrame: 
    
    # todo: update references to shapely.Point(x.geometry.coords[0])
    # we can use shapely.get_point()
    keep_cols =  ["trip_instance_key", "shape_array_key",
                   "stop_sequence", "stop_id", "stop_pair", 
                   #"stop_primary_direction",
                   "geometry"]

    proxy_stops = longer_segments.assign(
        geometry = longer_segments.apply(
            lambda x: shapely.get_point(x.geometry, 0), axis=1)
    ).rename(
        columns = {"stop_id1": "stop_id"}
    )[keep_cols + ["stop_sequence1"]].to_crs(geography_utils.WGS84)

    # stop_primary_direction can be populated when it's appended
    # with the stop_times, and we can sort by trip-stop_sequence1
    # and pd.ffill (forward fill)
    stop_times = helpers.import_scheduled_stop_times(
        analysis_date,
        columns = ["trip_instance_key", "shape_array_key",
                   "stop_sequence", "stop_id", "stop_pair", 
                   "stop_primary_direction",
                   "geometry"],
        with_direction = True,
        get_pandas = True,
        crs = geography_utils.WGS84,
    )
    
    trip_stop_cols = ["trip_instance_key", "stop_sequence"]
    
    gdf = pd.concat(
        [stop_times.assign(proxy_stop=0), 
         proxy_stops.assign(proxy_stop=1)], 
        axis=0, ignore_index=True
    ).sort_values(
        trip_stop_cols
    ).reset_index(drop=True)
    
    gdf = gdf.assign(
        stop_primary_direction = (gdf.groupby(trip_stop_cols)
                                  .stop_primary_direction
                                  .ffill()
                                 ),
        #TODO: create stop_sequence2 
        # is this needed or will stop_sequence1 be sufficient
        # segments go from current stop to next stop, 
    ).pipe(gtfs_schedule_wrangling.fill_missing_stop_sequence1)
    
    # After filling in stop_primary_direction, we need a drop_duplicates
    # and keep the row where proxy_stop==1 wherever there are dupes
    gdf = gdf.sort_values(
        trip_stop_cols + ["proxy_stop"], 
        ascending = [True for i in trip_stop_cols] + [False]
    ).drop_duplicates(
        subset=trip_stop_cols
    ).reset_index(drop=True)
    
    return gdf


if __name__ == "__main__":
    
    LOG_FILE = "../logs/cut_stop_segments.log"
    logger.add(LOG_FILE, retention="3 months")
    logger.add(sys.stderr, 
               format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}", 
               level="INFO") 
    
    #from segment_speed_utils.project_vars import analysis_date_list
    from shared_utils import rt_dates
    
    for analysis_date in [rt_dates.DATES["mar2024"]]:
        start = datetime.datetime.now()
        
        SEGMENT_LENGTH = GTFS_DATA_DICT.speedmap_segments.segment_meters
        ALL_STOP_SEGMENTS = GTFS_DATA_DICT.rt_stop_times.segments_file
        
        # Two export files
        SPEEDMAP_SEGMENTS = GTFS_DATA_DICT.speedmap_segments.segments_file
        SPEEDMAP_STOP_TIMES = GTFS_DATA_DICT.speedmap_segments.proxy_stop_times
        
        stop_segments = gpd.read_parquet(
            f"{SEGMENT_GCS}{ALL_STOP_SEGMENTS}_{analysis_date}.parquet",
        )

        stop_segments = stop_segments.assign(
            segment_length = stop_segments.geometry.length
        )
                        
        longer_segments = cut_longer_segments(
            stop_segments, 
            SEGMENT_LENGTH
        )

        time1 = datetime.datetime.now()
        logger.info(f"cut longer segments: {time1 - start}")
        '''      
        speedmap_segments = pd.concat([
            stop_segments.loc[stop_segments.segment_length < SEGMENT_LENGTH],
            longer_segments], 
            axis=0
        ).drop(
            columns = ["segment_length"]
        ).pipe(
            gtfs_schedule_wrangling.fill_missing_stop_sequence1
        ).sort_values(
            ["schedule_gtfs_dataset_key", 
            "trip_instance_key", "stop_sequence1"]
        ).reset_index(drop=True)
        # need to fill in missing because when we concat,
        # the segments that were shorter do not have values for stop_sequence1
        
        utils.geoparquet_gcs_export(
            speedmap_segments,
            SEGMENT_GCS,
            f"{SPEEDMAP_SEGMENTS}_{analysis_date}"
        )
        ''' 
        time2 = datetime.datetime.now()
        logger.info(f"concatenate segments and export: {time2 - time1}")

        #del stop_segments, speedmap_segments
        
        speedmap_stops = get_proxy_stops(longer_segments, analysis_date)
        end = datetime.datetime.now()
        
        logger.info(f"concatenate and export new stop times: {end - time2}")
        
        utils.geoparquet_gcs_export(
            speedmap_stops,
            SEGMENT_GCS,
            f"{SPEEDMAP_STOP_TIMES}_{analysis_date}"
        )
          
        logger.info(f"execution time: {end - start}")