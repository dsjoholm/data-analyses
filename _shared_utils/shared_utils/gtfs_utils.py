"""
GTFS utils.

Queries to grab trips, stops, routes.

TODO: move over some of the rt_utils
over here, if it addresses GTFS schedule data more generally,
such as cleaning/reformatting arrival times.

Leave the RT-specific analysis there.
"""
import datetime

import geopandas as gpd
import pandas as pd
from calitp.tables import tbl
from shared_utils import geography_utils
from siuba import *

# import os
# os.environ["CALITP_BQ_MAX_BYTES"] = str(200_000_000_000)


YESTERDAY_DATE = datetime.date.today() + datetime.timedelta(days=-1)


METROLINK_SHAPE_TO_ROUTE = {
    "AVin": "Antelope Valley Line",
    "AVout": "Antelope Valley Line",
    "OCin": "Orange County Line",
    "OCout": "Orange County Line",
    "LAXin": "LAX FlyAway Bus",
    "LAXout": "LAX FlyAway Bus",
    "SBin": "San Bernardino Line",
    "SBout": "San Bernardino Line",
    "VTin": "Ventura County Line",
    "VTout": "Ventura County Line",
    "91in": "91 Line",
    "91out": "91 Line",
    "IEOCin": "Inland Emp.-Orange Co. Line",
    "IEOCout": "Inland Emp.-Orange Co. Line",
    "RIVERin": "Riverside Line",
    "RIVERout": "Riverside Line",
}

METROLINK_ROUTE_TO_SHAPE = dict((v, k) for k, v in METROLINK_SHAPE_TO_ROUTE.items())


def fill_in_metrolink_trips_df_with_shape_id(trips: pd.DataFrame) -> pd.DataFrame:
    """
    trips: pandas.DataFrame.
            What is returned from tbl.views.gtfs_schedule_dim_trips()
            or some dataframe derived from that.

    Returns only Metrolink rows, with shape_id filled in.
    """
    # Even if an entire routes df is supplied, subset to just Metrolink
    df = trips[trips.calitp_itp_id == 323].reset_index(drop=True)

    # direction_id==1 (inbound), toward LA Union Station
    # direction_id==0 (outbound), toward Irvine/Oceanside, etc

    df = df.assign(
        shape_id=df.route_id.apply(lambda x: METROLINK_ROUTE_TO_SHAPE[x])
        .str.replace("in", "")
        .str.replace("out", "")
    )

    # OCin and OCout are not distinguished in dictionary
    df = df.assign(
        shape_id=df.apply(
            lambda x: x.shape_id + "out"
            if x.direction_id == "0"
            else x.shape_id + "in",
            axis=1,
        )
    )

    return df


def get_route_info(
    selected_date: str | datetime.date = YESTERDAY_DATE,
    itp_id_list: list[int] = None,
    route_cols: list[str] = None,
    get_df: bool = True,
) -> pd.DataFrame:

    # Route info query
    dim_routes = tbl.views.gtfs_schedule_dim_routes() >> distinct()

    routes = (
        tbl.views.gtfs_schedule_fact_daily_feed_routes()
        >> filter(_.date == selected_date)
        >> inner_join(
            _, dim_routes, on=["route_key", "calitp_extracted_at", "calitp_deleted_at"]
        )
        >> distinct()
    )

    if itp_id_list is not None:
        routes = routes >> filter(_.calitp_itp_id.isin(itp_id_list))

    if route_cols is not None:
        routes = routes >> select(*route_cols)

    if get_df is True:
        routes = routes >> collect()

    return routes


def get_stops(
    selected_date: str | datetime.date = YESTERDAY_DATE,
    itp_id_list: list[int] = None,
    stop_cols: list[str] = None,
    get_df: bool = True,
) -> gpd.GeoDataFrame:

    # Stops query
    dim_stops = tbl.views.gtfs_schedule_dim_stops() >> distinct()

    stops = (
        tbl.views.gtfs_schedule_fact_daily_feed_stops()
        >> filter(_.date == selected_date)
        >> inner_join(
            _, dim_stops, on=["stop_key", "calitp_extracted_at", "calitp_deleted_at"]
        )
        >> distinct()
    )

    if itp_id_list is not None:
        stops = stops >> filter(_.calitp_itp_id.isin(itp_id_list))

    if stop_cols is not None:
        stops = stops >> select(*stop_cols)

    if get_df is True:
        stops = geography_utils.create_point_geometry(stops >> collect()).drop(
            columns=["stop_lon", "stop_lat"]
        )

    return stops


def get_trips(
    selected_date: str | datetime.date = YESTERDAY_DATE,
    itp_id_list: list[int] = None,
    trip_cols: list[str] = None,
    get_df: bool = True,
) -> pd.DataFrame:

    # Trips query
    dim_trips = tbl.views.gtfs_schedule_dim_trips() >> distinct()

    trips = (
        tbl.views.gtfs_schedule_fact_daily_trips()
        >> filter(_.service_date == selected_date, _.is_in_service == True)
        >> inner_join(
            _,
            dim_trips,
            on=[
                "trip_key",
                "trip_id",
                "route_id",
                "service_id",
                "calitp_itp_id",
                "calitp_url_number",
                "calitp_extracted_at",
                "calitp_deleted_at",
            ],
        )
        >> distinct()
    )

    if itp_id_list is not None:
        trips = trips >> filter(_.calitp_itp_id.isin(itp_id_list))

    if trip_cols is not None:
        trips = trips >> select(*trip_cols)

    if get_df is True:
        trips = trips >> collect()

    return trips


def get_trips_with_stop_times(
    selected_date: str | datetime.date = YESTERDAY_DATE,
    itp_id_list: list[int] = None,
    departure_hours: list[int] = None,
    trip_stop_time_cols: list[str] = None,
    get_df: bool = True,
) -> pd.DataFrame:

    trips = get_trips(
        selected_date=selected_date,
        itp_id_list=itp_id_list,
        trip_cols=None,
        get_df=False,
    )

    # Join to stop_times, since stop_times always depends on trip_id
    # No other way to filter stop_times by date
    trips_with_stop_times = tbl.views.gtfs_schedule_dim_stop_times() >> inner_join(
        _,
        # Drop these columns,
        # the inner join will either return 0 rows or _x, _y
        # Can't use in merge_cols
        # because they are different values
        trips >> select(-_.calitp_hash, -_.calitp_extracted_at, -_.calitp_deleted_at),
        on=["calitp_itp_id", "calitp_url_number", "trip_id"],
    )

    if itp_id_list is not None:
        trips_with_stop_times = trips_with_stop_times >> filter(
            _.calitp_itp_id.isin(itp_id_list)
        )

    if trip_stop_time_cols is not None:
        trips_with_stop_times = trips_with_stop_times >> select(*trip_stop_time_cols)

    if get_df is True:
        trips_with_stop_times = trips_with_stop_times >> collect()

    return trips_with_stop_times
