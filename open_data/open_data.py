"""
Track the metadata updates for all open data portal datasets.
"""
from pathlib import Path

import metadata_update_pro
from update_vars import XML_FOLDER, META_JSON, RUN_ME


if __name__=="__main__":
    assert str(Path.cwd()).endswith("open_data"), "this script must be run from open_data directory!"
    
    for i in RUN_ME:
        print(i)
        print("-------------------------------------------")
        metadata_update_pro.update_dataset_metadata_xml(
            i, 
            metadata_path = META_JSON,
        )