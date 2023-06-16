"""
Track the metadata updates for all open data portal datasets.
"""
import os

import metadata_update_pro

# Import various dictionaries
import metadata_hqta
import metadata_traffic_ops
# import metadata_speeds

OPEN_DATA = {
    "hqta_areas": {
        "path": "./metadata_xml/ca_hq_transit_areas.xml", 
        "metadata_dict": metadata_hqta.HQTA_TRANSIT_AREAS_DICT,
    },
    "hqta_stops": {
        "path": "./metadata_xml/ca_hq_transit_stops.xml",
        "metadata_dict": metadata_hqta.HQTA_TRANSIT_STOPS_DICT,
    },
    "transit_stops": {
        "path": "./metadata_xml/ca_transit_stops.xml",
        "metadata_dict": metadata_traffic_ops.STOPS_DICT,
    },
    "transit_routes": {
        "path": "./metadata_xml/ca_transit_routes.xml",
        "metadata_dict": metadata_traffic_ops.ROUTES_DICT,
    },
    #"speeds_stop_segments": {
    #    "path": "./metadata_xml/ca_speeds_stop_segments.xml",
    #    "metadata_dict": metadata_speeds.SPEEDS_STOP_SEG_DICT,
    #},
}

if __name__=="__main__":
    assert os.getcwd().endswith("open_data"), "this script must be run from open_data directory!"

    RUN_ME = [
        "hqta_areas", "hqta_stops",
        "transit_stops", "transit_routes",
        #"speeds_stop_segments",
    ]
    
    for name, dataset in OPEN_DATA.items():
        if name in RUN_ME:
            print(name)
            print("-------------------------------------------")
            metadata_update_pro.update_metadata_xml(
                dataset["path"], 
                dataset["metadata_dict"], 
                first_run=True)
    
