import geopandas as gpd
import numpy as np
import pandas as pd
from calitp import *
from shared_utils import utils

GCS_FILE_PATH = "gs://calitp-analytics-data/data-analyses/pmp_dashboard/"

'''
Crosswalks, Lists, Variables
'''
#Group PEC Class descriptions into divisions
div_crosswalks= {
            "State & Fed Mass Trans": "DRMT",
            "Statewide Planning": "DOTP",
            "Research": "DRISI",
            "PSR/PSSR Development": "DOTP",
            "Rail": "DRMT",
            "Planning Administration": "DOTP",
            "Regional Planning": "DOTP",
        }

#A list to hold clean dataframes
my_clean_dataframes = []

'''
Functions that can be used across sheets
'''
def cleaning_psoe_tpsoe(df, ps_or_oe: str):
    """ 
    Cleaning the PSOE and TPSOE sheets
    prior to concating them by stripping columns of their prefixes   
    """
    df["type"] = ps_or_oe

    """
    Strip away the prefixes from column names
    https://stackoverflow.com/questions/54097284/removing-suffix-from-dataframe-column-names-python
    Create suffix
    """
    suffix = f"{ps_or_oe}_"
    df.columns = df.columns.str.replace(suffix, "", regex=True)

    return df

'''
Function that loads & cleans raw data
'''
int_cols = [
    "ps_allocation",
    "ps_expenditure",
    "ps_balance",
    "ps_projection",
    "py_pos_alloc",
    "act__hours",
    "oe_allocation",
    "oe_encumbrance",
    "oe_expenditure",
    "oe_balance",
    "total_allocation",
    "total_expenditure",
    "total_balance",
    "total_projection",
    "ap"
]


def import_raw_data(file_name: str, name_of_sheet: str, appropriations_to_filter: list):

    """Load the raw data and clean it up.

    Args:
        file_name: the Excel workbook
        name_of_sheet: the name of the sheet
        appropriations_to_filter: list of all the appropriations to be filtered out

    Returns:
        The cleaned df. Input the results into a list.

    """
    df = pd.read_excel(f"{GCS_FILE_PATH}{file_name}", sheet_name=name_of_sheet)

    # Get rid of the unnecessary header info
    # Stuff like "Enterprise Datalink Production download as of 05/23/2022"
    df = df.iloc[13:].reset_index(drop=True)

    # The first row contains column names - update it to the column
    df.columns = df.iloc[0]

    # Drop the first row as they are now column names
    df = df.drop(df.index[0]).reset_index(drop=True)

    # Drop rows with NA in PEC Class
    # Since those are probably the grand totals tagged at the end of the Excel sheet
    df = df.dropna(subset=["PEC Class"])

    # Snakecase
    df = to_snakecase(df)

    # Rename columns to mimc dashboard
    df = df.rename(
        columns={
            "ps_alloc": "ps_allocation",
            "ps_exp": "ps_expenditure",
            "ps_bal": "ps_balance",
            "total_projected_%": "total_%_expended",
            "oe_alloc": "oe_allocation",
            "oe_enc": "oe_encumbrance",
            "oe_exp": "oe_expenditure",
            "appr": "appropriation",
            "total_expended___encumbrance": "total_expenditure",
            "oe_bal_excl_pre_enc": "oe_balance",
        }
    )
    
    """
    Drop Projection Cols & Recreate
    """
    
    try:
        df = df.drop(columns="oe_projection")
    except:
        pass
    
    try:
        df = df.drop(columns="oe__enc_+_oe_exp_projection")
    except:
        pass
    
    # Change to the right data type
    df[int_cols] = df[int_cols].astype("int64")
    
    # Add the column of 'Year End Expended Pace'
    df["year_expended_pace"] = (df["ps_projection"] / df["ps_allocation"]).fillna(0)
    
    # Create oe__enc_+_oe_exp_projection
    df['oe_projection'] = (df['oe_encumbrance']+df['oe_expenditure']/(df.iloc[0]['ap'])*12).astype('int64')
    
    # Certain appropriation(s) are filtered out:
    df = df[~df.appropriation.isin(appropriations_to_filter)]

    # Narrow down division names inot a new column
    df["division"] = df["pec_class_description"].replace(div_crosswalks)

    # Adding dataframe to an empty list called my_clean_dataframes
    my_clean_dataframes.append(df)
    
    return df

'''
Funds by Division Sheet
'''
def create_fund_by_division(df):
    # Drop excluded cols
    excluded_cols = ["appr_catg", "act__hours", "py_pos_alloc", "pec_class_description", "ap"]
    df = df.drop(columns=excluded_cols)
    
    # Add a blank column for notes
    df["notes"] = np.nan

    
    return df

'''
TPSOE Sheet
'''
# Columns relevant PS
tpsoe_ps_list = [
    "fund",
    "fund_description",
    "appropriation",
    "pec_class",
    "division",
    "ps_allocation",
    "ps_expenditure",
    "ps_balance",
    "ps_projection",
    "year_expended_pace",
    "ps_%_expended",
]

# Columns relevant OE
tpsoe_oe_list = [
    "fund",
    "fund_description",
    "appropriation",
    "pec_class",
    "division",
    "oe_allocation",
    "oe_encumbrance",
    "oe_expenditure",
    "oe_balance",
    "oe_projection",
]

# Monetary columns
monetary_cols = [
    "allocation",
    "expenditure",
    "balance",
    "encumbrance",
    "projection",
]

# Ordering the columns correctly
order_of_cols = [
    "pec_class",
    "division",
    "fund",
    "fund_description",
    "appropriation",
    "type",
    "allocation",
    "expenditure",
    "balance",
    "encumbrance",
    "projection",
    "year_expended_pace",
    "%_expended",
]

# Create the sheet
def create_tpsoe(df, ps_list: list, oe_list: list):
    """
    ps_list: a list of all the ps related columns.
    oe_list: a list of all the oe related columns.
    Use this to subset out the whole dataframe,
    one for personal services, one for operating expenses.
    """

    # Clean up and subset out the dataframe
    tpsoe_oe = cleaning_psoe_tpsoe(df[oe_list], "oe")
    tpsoe_ps = cleaning_psoe_tpsoe(df[ps_list], "ps")

    # Concat the two dataframes together
    c1 = pd.concat([tpsoe_ps, tpsoe_oe], sort=False)

    # Rearrange the columns to the right order
    c1 = c1[order_of_cols]

    # Add a notes column
    c1["notes"] = np.nan

    # Correct data types of monetary columns from objects to float
    c1[monetary_cols] = c1[monetary_cols].astype("float64")

    return c1

'''
Timeline Sheet
'''
def create_timeline(my_clean_dataframes:list):
    """
    Stack all the dfs in my_clean_dataframes
    """
    c1 = pd.concat(my_clean_dataframes, sort = False)
    
    return c1

'''
PSOE Timeline
'''
# Columns relevant PS
psoe_ps_cols = [
    "appr_catg",
    "fund",
    "fund_description",
    "appropriation",
    "pec_class",
    "division",
    "ps_allocation",
    "ps_expenditure",
    "ps_balance",
    "ps_projection",
    "ps_%_expended",
    "ap",
    "pec_class_description",
]

# Columns relevant OE
psoe_oe_cols = [
    "appr_catg",
    "fund",
    "fund_description",
    "appropriation",
    "pec_class",
    "division",
    "oe_allocation",
    "oe_encumbrance",
    "oe_expenditure",
    "oe_balance",
    "oe_projection",
    "oe_%_expended",
    "ap",
    "pec_class_description",
]

# Reorder to the right column
psoe_right_col_order = [
    "appr_catg",
    "fund",
    "fund_description",
    "appropriation",
    "division",
    "pec_class",
    "pec_class_description",
    "allocation",
    "expense",
    "balance",
    "projection",
    "%_expended",
    "ap",
    "type",
    "encumbrance",
]

def create_psoe_timeline(df, ps_list: list, oe_list: list):

    # Create 2 dataframes that subsets out OE and PS
    psoe_oe = cleaning_psoe_tpsoe(df[oe_list], "oe")
    psoe_ps = cleaning_psoe_tpsoe(df[ps_list], "ps")

    # Stack both dataframes on top of each other
    c1 = pd.concat([psoe_ps, psoe_oe], sort=False)

    # Rename column
    c1 = c1.rename(columns={"expenditure": "expense"})

    # Rearrange the dataframe in the right order
    c1 = c1[psoe_right_col_order]

    return c1