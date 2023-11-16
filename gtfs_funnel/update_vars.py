import yaml
from pathlib import Path
from shared_utils import rt_dates

months = ["nov"]         

analysis_date_list = [
    rt_dates.DATES[f"{m}2023"] for m in months
]

CONFIG_PATH = Path("config.yml")

with open(CONFIG_PATH) as f: 
    CONFIG_DICT = yaml.safe_load(f)  