"""
Track the metadata updates for all open data portal datasets.
"""
import metadata_update

# Import various dictionaries
import hqta
import traffic_ops

OPEN_DATA = {
    "hqta_areas": {
        "path": "./metadata_xml/ca_hq_transit_areas.xml", 
        "metadata_dict": hqta.HQTA_TRANSIT_AREAS_DICT,
    },
    "hqta_stops": {
        "path": "./metadata_xml/ca_hq_transit_stops.xml",
        "metadata_dict": hqta.HQTA_TRANSIT_STOPS_DICT,
    },
    "transit_stops": {
        "path": "./metadata_xml/ca_transit_stops.xml",
        "metadata_dict": traffic_ops.STOPS_DICT,
    },
    "transit_routes": {
        "path": "./metadata_xml/ca_transit_routes.xml",
        "metadata_dict": traffic_ops.ROUTES_DICT,
    },
}

if __name__=="__main__":
    RUN_ME = ["test"]
    
    for name, dataset in OPEN_DATA.items():
        if name in RUN_ME:
            print(name)
            print("-------------------------------------------")
            metadata_update.update_metadata_xml(dataset["path"], 
                                                dataset["metadata_dict"], 
                                                first_run=True)
