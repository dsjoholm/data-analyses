import os
import arcpy

from arcpy import metadata as md

arcpy.env.workspace = os.path.join("C:\\", "Users", "s153936", "Documents", "ArcGIS")
working_dir = arcpy.env.workspace

# Set local variables
in_features = [
    'ca_hq_transit_areas',
    'ca_hq_transit_stops',
    'ca_transit_routes',
    'ca_transit_stops',
    'speeds_by_stop_segments',
    'speeds_by_route_time_of_day',
]

staging_location = 'staging.gdb'
out_location = 'open_data.gdb'

# Path to Metadata stylesheet
directory = arcpy.GetInstallInfo("desktop")["InstallDir"] 
TRANSLATOR = "ISO19139_GML32" 

def feature_class_in_gdb_path(my_gdb, file_name):
    return os.path.join(my_gdb, file_name)


# Clean up last run (if applicable)
for f in in_features:
    feature_path = f"{working_dir}\{f}.xml"
    if os.path.exists(feature_path):
        os.remove(feature_path)

## (1) Convert shapefile layer to gdb feature class
for f in in_features:
    # construct the filename, which is takes form of routes_assembled/routes_assembled.shp
    shp_file_name = f"{os.path.join(f, f'{f}.shp')}"
    
    this_feature_class = feature_class_in_gdb_path(staging_location, f)
    if arcpy.Exists(this_feature_class): 
        arcpy.management.Delete(this_feature_class)

    # Execute FeatureClassToGeodatabase
    arcpy.FeatureClassToGeodatabase_conversion(shp_file_name, staging_location)
    
    # Print field names, just in case it needs renaming
    field_list = arcpy.ListFields(
        os.path.join(staging_location, f))  #get a list of fields for each feature class
    
    for field in field_list: #loop through each field
        print(field.name)

## (2) Rename fields where needed
# Do this once it's a feature class, so we can preserve the new column names
# before metadata is created
hqta_renaming = [
    'ca_hq_transit_areas',
    'ca_hq_transit_stops',
]
speed_renaming = [
    'speeds_by_stop_segments',
    'speeds_by_route_time_of_day'
]

# hqta datasets
RENAME_HQTA = {
    "agency_pri": "agency_primary",
    "agency_sec": "agency_secondary",
    "hqta_detai": "hqta_details",
    "base64_url": "base64_url_primary",
    "base64_u_1": "base64_url_secondary",  
    "org_id_pri": "org_id_primary",
    "org_id_sec": "org_id_secondary",
}

# speeds datasets
RENAME_SPEED = {
    "stop_seque": "stop_sequence",
    "time_of_da": "time_of_day",
    "district_n": "district_name",
    "direction_": "direction_id",
    "common_sha": "common_shape_id",
    "avg_sched_": "avg_sched_service_min", 
    "avg_rt_tri": "avg_rt_service_min",
}

# Separate out renaming for groups of datasets to prevent 
# columns from being renamed when we don't want it to (don't need suffixes for non-hqta)
def rename_columns_with_dict(feature_class_list, rename_dict):
    for f in feature_class_list:
        # To change field names, must use AlterField_management, 
        # because changing it in XML won't carry through when you sync
        this_feature_class = feature_class_in_gdb_path(staging_location, f)

        field_list = arcpy.ListFields(this_feature_class)  #get a list of fields for each feature class    

        for field in field_list: #loop through each field
            if field.name in rename_dict:  #look for the name elev
                arcpy.AlterField_management(
                    this_feature_class, 
                    field.name, rename_dict[field.name], # new_field_name
                    rename_dict[field.name]) # new_field_alias
    return
            

            
rename_columns_with_dict(hqta_renaming, RENAME_HQTA)
rename_columns_with_dict(speed_renaming, RENAME_SPEED)
            
            
# Double check it's done
# TODO: this does look like it renames it...but when XML is exported in next step
# the new field names are not retained
for f in hqta_renaming + speed_renaming:
    this_feature_class = os.path.join(staging_location, f)

    # Print field names, just in case it needs renaming
    field_list = arcpy.ListFields(this_feature_class)  #get a list of fields for each feature class
    
    print(this_feature_class)
    for field in field_list: #loop through each field
        print(field.name)


## (3) Export metadata associated with file gdb feature class in FGDC format    
for f in in_features:
    this_feature_class = feature_class_in_gdb_path(staging_location, f)

    # Original metadata
    # Migrating to Pro: https://pro.arcgis.com/en/pro-app/latest/arcpy/metadata/migrating-from-arcmap-to-arcgis-pro.htm

    source_metadata = md.Metadata(this_feature_class)

    # Export metadata XML    
    meta_output = os.path.join(working_dir, f"{f}.xml")
        
    # In ArcGIS Pro, instead of FGDC for Desktop, use ISO 19139 GML 3.2
    # https://sv03tmcpo.ct.dot.ca.gov/portal/apps/sites/#/geep/pages/open-data-request
    TRANSLATOR = "ISO19139_GML32" 
    
    source_metadata.exportMetadata(outputPath = meta_output,
                                   metadata_export_option=TRANSLATOR)
    
    print(f"successful export: {f}")


### (4) UPDATE XML METADATA SEPARATELY IN PYTHON OUTSIDE OF ARCGIS IN JUPYTERHUB

## Do a manual import metadata in ArcGIS Pro to update XML for staging feature classes

## (5) Copy the feature class from staging location to out location
# Use staging location and out location because otherwise, arcpy errors when it detects
# another XML when you try and update the layer in a subsequent update
for f in in_features:
    # Delete the feature class in this gdb, because we don't want _1 appended to end
    staging_feature_class = feature_class_in_gdb_path(staging_location, f)
    out_feature_class = feature_class_in_gdb_path(out_location, f)

    if arcpy.Exists(out_feature_class): 
        arcpy.management.Delete(out_feature_class)

    # Copy over the feature class from staging.gdb to open_data.gdb
    # Since we already manually imported XML in staging, 
    # when this feature class is moved to out_location, it takes the new XML with it
    arcpy.conversion.FeatureClassToFeatureClass(staging_feature_class, 
                                                out_location, 
                                                f)


## (7) Move from file gdb to enterprise gdb
# License Select must be set to Advanced for this to work
# Exit and restart ArcPro to clear locks on layers in overwriting
# If we don't exit, the layer will be locked because it shows we're already using it 
# staging to open_data), and it will prevent writing from open_data to the enterprise gdb.

ENTERPRISE_DATABASE = "Database Connections/HQrail(edit)@sv03tmcsqlprd1.sde"

for f in in_features:
    out_feature_class = feature_class_in_gdb_path(out_location, f)
    
    arcpy.FeatureClassToFeatureClass_conversion(
        in_features = out_feature_class,
        out_path = ENTERPRISE_DATABASE,
        out_name = f)