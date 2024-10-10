"""
Functions that are used across _section_1_utils and _section_2_utils.
"""
import calitp_data_analysis.magics
import geopandas as gpd
import pandas as pd
import yaml

from great_tables import GT, loc, style

def labeling(word: str) -> str:
    """
    """
    return (
        word.replace("_", " ")
        .title()
        .replace("Pct", "%")
        .replace("Vp", "VP")
        .replace("Route Combined Name", "Route")
        .replace("Ttl", "Total")
    )

with open("readable.yml") as f:
    readable_dict = yaml.safe_load(f)
    
def replace_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Replace columnn names with a more readable name 
    found in readable_dict.yml.
    """
    def replace_single_column(column_name: str):
        if column_name in readable_dict:
            if 'readable' in readable_dict[column_name]:
                return readable_dict[column_name]['readable']
            else:
                return readable_dict[column_name]
        return column_name
    
    df = df.rename(columns = {
        **{c: replace_single_column(c) for c in df.columns}
    })
    
    return df


def district_stats(
    df: pd.DataFrame, 
    group_cols: list
) -> pd.DataFrame:
    """
    Get district metrics by summing or taking average across 
    all operators in the district for GTFS schedule data.
    """
    sum_me = [
        f"operator_n_{i}" for i in [
            "routes", "trips", "stops", "arrivals"]
    ]
    
    df2 = (df.groupby(group_cols, 
                      observed=True, group_keys=False)
           .agg({
               "name": "nunique",
               **{c:"sum" for c in sum_me},
           })
           .reset_index()
           .rename(columns = {"name": "n_operators"})
          )
    
    # These need to be calculated again separately
    df2 = df2.assign(
        arrivals_per_stop = df2.operator_n_arrivals.divide(
            df2.operator_n_stops).round(2),
        trips_per_operator = df2.operator_n_trips.divide(df2.n_operators).round(2)
    )
    
    return df2


def transpose_summary_stats(
    df: pd.DataFrame, 
    district_col: str = "caltrans_district"
) -> pd.DataFrame:
    """
    District summary should be transposed, otherwise columns
    get shrunk and there's only 1 row.
    
    Do some wrangling here so that great tables
    can display it fairly cleanly.
    """
    # Fix this so we can see it
    subset_df = df.drop(
        columns = district_col
    ).reset_index(drop=True)
    
    subset_df2 = subset_df.rename(
        columns = {
            **{c: f"{c.replace('operator_n_', '# ')}" for c in subset_df.columns},
            "n_operators": "# operators",
            "arrivals_per_stop": "arrivals per stop",
            "trips_per_operator": "trips per operator"
        }).T.reset_index().rename(columns = {0: "value"})
    
    return subset_df2


def great_table_formatting(my_table: GT) -> GT:
    """
    """
    my_table = (
        my_table
        .opt_align_table_header(align="center")
        .tab_style(
            style=style.text(size="14px"),
            locations=loc.body())
        .tab_options(
            container_width = "100%",
            table_background_color="white",
            table_body_hlines_style="none",
            table_body_vlines_style="none",
            heading_background_color="white",
            column_labels_background_color="white",
            row_group_background_color="white",
            stub_background_color="white",
            source_notes_background_color="white"
         )
    )
    
    return my_table

