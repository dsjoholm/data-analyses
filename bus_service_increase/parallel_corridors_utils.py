"""
"""
import altair as alt
import intake
import pandas as pd

from IPython.display import display, Markdown, HTML

import setup_parallel_trips_with_stops
import utils
from shared_utils import calitp_color_palette as cp
from shared_utils import styleguide

alt.themes.register("calitp_theme", styleguide.calitp_theme)

catalog = intake.open_catalog("./*.yml")

SELECTED_DATE = '2022-1-6' #warehouse_queries.dates['thurs']

def operator_parallel_competitive_stats(itp_id, pct_trips_competitive_cutoff):
    '''
    DATA_PATH = f"{utils.GCS_FILE_PATH}2022_Jan/"

    # Read in intermediate parquet for trips on selected date
    trips = pd.read_parquet(f"{DATA_PATH}trips_joined_thurs.parquet")

    # Attach service hours
    # This df is trip_id-stop_id level
    trips_with_service_hrs = setup_parallel_trips_with_stops.grab_service_hours(
        trips, SELECTED_DATE)

    trips_with_service_hrs.to_parquet("./data/trips_with_service_hours.parquet")
    '''    
    df = pd.read_parquet("./data/trips_with_service_hours.parquet")
    df = df[df.calitp_itp_id==itp_id]
    
    parallel_df = setup_parallel_trips_with_stops.subset_to_parallel_routes(df)
    
    competitive_df = catalog.competitive_route_variability.read()
    competitive_df = competitive_df[
        (competitive_df.calitp_itp_id == itp_id) & 
        (competitive_df.pct_trips_competitive > pct_trips_competitive_cutoff)
    ]
    
    operator_dict = {
        "num_routes": df.route_id.nunique(),
        "parallel_routes": parallel_df.route_id.nunique(),
        "competitive_routes": competitive_df.route_id.nunique(),
    }
    
    return operator_dict

#------------------------------------------------------------#
# Stripplot
# #https://altair-viz.github.io/gallery/stripplot.html
#------------------------------------------------------------#
# Color to designate p25, p50, p75, fastest trip?
DARK_GRAY = "#323434"
NAVY = cp.CALITP_CATEGORY_BOLD_COLORS[0]

def labeling(word):
    label_dict = {
        "bus_multiplier": "Ratio of Bus to Car Travel Time",
        "bus_difference": "Difference in Bus to Car Travel Time (min)"
    }
    
    if word in label_dict.keys():
        word = label_dict[word]
    else:
        word = word.replace('_', ' ').title()
    
    return word


def specific_point(y_col):
    chart = (
        alt.Chart()
        .mark_point(size=20, opacity=0.6, strokeWidth=1.3)
        .encode(
            y=alt.Y(f'{y_col}:Q'),
            color=alt.value(DARK_GRAY)
        )
    )
    
    return chart


def set_yaxis_range(df, y_col):
    Y_MIN = df[y_col].min()
    Y_MAX = df[y_col].max()
    
    return Y_MIN, Y_MAX


def make_stripplot(df, y_col="bus_multiplier", Y_MIN=0, Y_MAX=5):  
    # max_trip_route_group is in hours, convert to minutes to match bus_difference units
    plus25pct_travel_minutes = df.max_trip_route_group.iloc[0] * 60 * 0.25
    df = df.assign(
        cutoff2 = plus25pct_travel_minutes
    )
    
    # We want to draw horizontal line on chart
    if y_col == "bus_multiplier":
        df = df.assign(cutoff=2)
    elif y_col == "bus_difference":
        df = df.assign(cutoff=0)
    
    # Use the same sorting done in the wrangling
    route_sort_order = list(df.sort_values(["calitp_itp_id", 
                                            "pct_trips_competitive", 
                                            "num_competitive",
                                            "p50"], 
                                       ascending=[True, False, False, True]
                                      )
                        .drop_duplicates(subset=["route_id"]).route_id)
        
    stripplot =  (
        alt.Chart()
          .mark_point(size=12, opacity=0.65, strokeWidth=1.1)
          .encode(
            x=alt.X(
                'jitter:Q',
                title=None,
                axis=alt.Axis(values=[0], ticks=True, grid=False, labels=False),
                scale=alt.Scale(),
                #stack='zero',
            ),
            y=alt.Y(f'{y_col}:Q', title=labeling(y_col), 
                    scale=alt.Scale(domain=[Y_MIN, Y_MAX])
                   ),
            color=alt.Color('time_of_day:N', title="Time of Day", 
                            sort=["AM Peak", "Midday", "PM Peak", "Owl Service"],
                            scale=alt.Scale(
                                # Grab colors where we can distinguish between groups
                                range=(cp.CALITP_CATEGORY_BOLD_COLORS
                                       #[:2] + 
                                       #cp.CALITP_CATEGORY_BOLD_COLORS[4:] 
                                      )
                            )
                           ),
            tooltip=alt.Tooltip(["route_id", "trip_id", 
                                 "service_hours", "car_duration_hours",
                                 "bus_multiplier", "bus_difference", 
                                 "num_trips", "num_competitive",
                                 "pct_trips_competitive",
                                 "p25", "p50", "p75"
                                ])
          )
        ).transform_calculate(
            # Generate Gaussian jitter with a Box-Muller transform
            jitter='sqrt(-2*log(random()))*cos(2*PI*random())'
    )
    
    p50 = (specific_point(y_col)
           .transform_filter(alt.datum.p50_trip==1)
          )

    horiz_line = (
        alt.Chart()
        .mark_rule(strokeDash=[2,3])
        .encode(
            y=alt.Y("cutoff:Q"),
            color=alt.value(DARK_GRAY)
        )
    )
    
    horiz_line2 = (
        alt.Chart()
        .mark_rule(strokeDash=[2,3])
        .encode(
            y=alt.Y("cutoff2:Q"),
            color=alt.value(NAVY)
        )
    )
    
    # Add labels
    # https://github.com/altair-viz/altair/issues/920
    text = (stripplot
            .mark_text(align='center', baseline='middle')
            .encode(
                x=alt.value(30),
                y=alt.value(15),
                text=alt.Text('pct_trips_competitive:Q', format='.0%'), 
                color=alt.value("black"))
           ).transform_filter(alt.datum.fastest_trip==1)
        
    # Must define data with top-level configuration to be able to facet
    if y_col == "bus_difference":
        other_charts = p50 + horiz_line + horiz_line2 + text
    else:
        other_charts = p50 + horiz_line + text
    
    chart = (
        (stripplot.properties(width=60) + 
         other_charts)
        .facet(
            column = alt.Column("route_id:N", title="Route ID",
                                sort = route_sort_order), 
            data=df,
        ).interactive()
        .configure_facet(spacing=0)
        .configure_view(stroke=None)
        .resolve_scale(y='shared')
        .properties(title=labeling(y_col))
    )
        
    return chart


PCT_COMPETITIVE_THRESHOLD = 0.75

def generate_report(df, PCT_COMPETITIVE_THRESHOLD = PCT_COMPETITIVE_THRESHOLD):
    # Set up df for charting (cut-off at some threshold to show most competitive routes)
    plot_me = (df[df.pct_trips_competitive > PCT_COMPETITIVE_THRESHOLD]
           .drop(columns = "geometry")
    )
    
    
    def top15_routes(df, route_group):
        df2 = (df[df.route_group==route_group])
        
        # Set a cut-off to enable sorting, where most of the trips are 
        # below a certain time difference cut-off, 
        # grab top 15 routes where majority of trips are below that cut-off 
        # cut-off done off of bus_difference because it's easier to understand
        bus_difference_cutoff = df2.bus_difference.quantile(0.25)
        
        route_cols = ["calitp_itp_id", "route_id"]
        
        df2 = df2.assign(
            below_cutoff = df2.apply(lambda x: 1 if x.service_hours <= bus_difference_cutoff 
                                     else 0, axis=1),
            num_trips = df2.groupby(route_cols)["trip_id"].transform("count")
        )
        
        df2["below_cutoff"] = df2.groupby(route_cols)["below_cutoff"].transform("sum")
        df2["pct_below_cutoff"] = df2.below_cutoff.divide(df2.num_trips)
        
        df3 = (df2
               .sort_values(["calitp_itp_id", "below_cutoff", 
                             "pct_below_cutoff", "route_id"],
                            ascending = [True, False, False, True]
                           )
               .drop_duplicates(subset=["calitp_itp_id", "route_id"])
              ).head(15)
                
        return list(df3.route_id)
    
    y_col1 = "bus_multiplier"
    Y_MIN1, Y_MAX1 = set_yaxis_range(plot_me, y_col1)

    y_col2 = "bus_difference"
    Y_MIN2, Y_MAX2 = set_yaxis_range(plot_me, y_col2)
    
    def combine_stripplots(df):
        multiplier_chart = make_stripplot(
            df, y_col1, Y_MIN = Y_MIN1, Y_MAX = Y_MAX1
        )


        difference_chart = make_stripplot(
            df, y_col2, Y_MIN = Y_MIN2, Y_MAX = Y_MAX2
        )
            
        return multiplier_chart, difference_chart
    
    
    short_routes= top15_routes(plot_me, "short")
    med_routes = top15_routes(plot_me, "medium")
    long_routes = top15_routes(plot_me, "long")
    
    s1, s2 = combine_stripplots(plot_me[plot_me.route_id.isin(short_routes)])
    m1, m2 = combine_stripplots(plot_me[plot_me.route_id.isin(med_routes)])
    l1, l2 = combine_stripplots(plot_me[plot_me.route_id.isin(long_routes)])
            
    display(HTML("<h3>Short Routes</h3>"))
    display(s1)
    display(s2)
    
    display(HTML("<h3>Medium Routes</h3>"))
    display(m1)
    display(m2)
    
    display(HTML("<h3>Long Routes</h3>"))
    display(l1)
    display(l2)