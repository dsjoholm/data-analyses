import os
os.environ["CALITP_BQ_MAX_BYTES"] = str(1_000_000_000_000) ## 1TB?

from siuba import *
import pandas as pd
import datetime as dt

# from calitp_data_analysis.tables import tbls
import shared_utils
from rt_analysis import rt_parser
import tqdm
import warnings

def stage_intermediate_data(row: pd.Series, pbar: tqdm.tqdm) -> None:
    '''
    Call using pd.apply for convienient iteration.
    Save progress to parquet after running each agency in case script is interrupted
    That progress parquet (when complete) is used in next script, actual output is ignored
    '''
    global speedmaps_index_joined
    analysis_date = row.analysis_date
    progress_path = f'./_rt_progress_{analysis_date}.parquet'
        
    if row.status != 'already_ran':
        try:
            rt_day = rt_parser.OperatorDayAnalysis(row.organization_itp_id,
                                                   analysis_date, pbar)
            rt_day.export_views_gcs()
            row.status = 'already_ran'
        except Exception as e:
            print(f'{row.organization_itp_id} parser failed: {e}')
            row.status = 'parser_failed'
        print(row.name)
        speedmaps_index_joined.loc[row.name] = row
        speedmaps_index_joined.to_parquet(PROGRESS_PATH)
    
    return  

if __name__ == "__main__":
    
    speedmaps_index_joined = shared_utils.rt_utils.check_intermediate_data()
    # check if this stage needed
    if speedmaps_index_joined.status.isin(['already_ran', 'parser_failed']).all():
        print('already attempted to stage all intermediate data:')
        print(f'{speedmaps_index_joined >> count(_.status)}')
    else:
        pbar = tqdm.tqdm()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _ = speedmaps_index_joined.apply(stage_intermediate_data, axis = 1, args=[pbar])