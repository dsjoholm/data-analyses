from shared_utils import rt_dates
import yaml
from pathlib import Path

#months = ["dec","nov", "oct", "sep", "aug",
#        "jul", "jun", "may", "apr", "mar"]         

analysis_date_list = [
    rt_dates.DATES[f"{m}2023"] for m in months
]

CONFIG_PATH = Path("config.yml")

with open(CONFIG_PATH) as f: 
    CONFIG_DICT = yaml.safe_load(f)  