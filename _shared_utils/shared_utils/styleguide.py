"""
Set Cal-ITP altair style template,
top-level configuration (for pngs),
and color palettes.

References:

Setting custom Altair theme as .py (Urban):
https://towardsdatascience.com/consistently-beautiful-visualizations-with-altair-themes-c7f9f889602

GH code:
https://github.com/chekos/altair_themes_blog/tree/master/notebooks

Download Google fonts:
https://gist.github.com/ravgeetdhillon/0063aaee240c0cddb12738c232bd8a49

Altair GH issue setting custom theme:
https://github.com/altair-viz/altair/issues/1333
https://discourse.holoviz.org/t/altair-theming/1421/2

https://stackoverflow.com/questions/33061785/can-i-load-google-fonts-with-matplotlib-and-jupyter

matplotlib:
https://github.com/CityOfLosAngeles/los-angeles-citywide-data-style

"""
from plotnine import *
from shared_utils import calitp_color_palette as cp

# --------------------------------------------------------------#
# Chart parameters
# --------------------------------------------------------------#
font_size = 18
chart_width = 400
chart_height = 250

markColor = "#8CBCCB"
axisColor = "#cbcbcb"
guideLabelColor = "#474747"
guideTitleColor = "#333"
blackTitle = "#333"
font = "Raleway"
labelFont = "Nunito Sans"
backgroundColor = "white"

PALETTE = {
    "category_bright": cp.CALITP_CATEGORY_BRIGHT_COLORS,
    "category_bold": cp.CALITP_CATEGORY_BOLD_COLORS,
    "diverging": cp.CALITP_DIVERGING_COLORS,
    "sequential": cp.CALITP_SEQUENTIAL_COLORS,
}


"""
# Run this in notebook
%%html
<style>
@import url('https://fonts.googleapis.com/css?family=Lato');
</style>
"""

# --------------------------------------------------------------#
# Altair
# --------------------------------------------------------------#


def calitp_theme(
    font=font,
    labelFont=labelFont,
    font_size=font_size,
    chart_width=chart_width,
    chart_height=chart_height,
    markColor=markColor,
    axisColor=axisColor,
    guideLabelColor=guideLabelColor,
    guideTitleColor=guideTitleColor,
    blackTitle=blackTitle,
    backgroundColor=backgroundColor,
    PALETTE=PALETTE,
):
    # Typography
    # At Urban it's the same font for all text but it's good to keep them separate in case you want to change one later.
    labelFont = labelFont
    sourceFont = labelFont

    return {
        # width and height are configured outside the config dict because they are Chart configurations/properties not chart-elements' configurations/properties.
        "width": chart_width,  # from the guide
        "height": chart_height,  # not in the guide
        "background": backgroundColor,
        "config": {
            "title": {
                "fontSize": font_size,
                "font": font,
                "anchor": "middle",
                "fontColor": blackTitle,
                "fontWeight": "bold",  # 300 was default. can also use lighter, bold, normal, bolder
                "offset": 20,
            },
            "header": {
                "labelFont": labelFont,
                "titleFont": font,
            },
            "axis": {
                "domain": True,
                "domainColor": axisColor,
                "grid": True,
                "gridColor": axisColor,
                "gridWidth": 1,
                "labelColor": guideLabelColor,
                "labelFontSize": 10,
                "titleColor": guideTitleColor,
                "tickColor": axisColor,
                "tickSize": 10,
                "titleFontSize": 12,
                "titlePadding": 10,
                "labelPadding": 4,
            },
            "axisBand": {
                "grid": False,
            },
            "range": {
                "category_bright": PALETTE["category_bright"],
                "category_bold": PALETTE["category_bold"],
                "diverging": PALETTE["diverging"],
                "sequential": PALETTE["sequential"],
            },
            "legend": {
                "labelFont": labelFont,
                "labelFontSize": 11,
                "symbolType": "square",
                "symbolSize": 30,  # default
                "titleFont": font,
                "titleFontSize": 14,
                "titlePadding": 10,
                "padding": 1,
                "orient": "right",
                # "offset": 0, # literally right next to the y-axis.
                "labelLimit": 0,  # legend can fully display text instead of truncating it
            },
            "view": {
                "stroke": "transparent",  # altair uses gridlines to box the area where the data is visualized. This takes that off.
            },
            "group": {
                "fill": backgroundColor,
            },
            # MARKS CONFIGURATIONS #
            "arc": {
                "fill": markColor,
            },
            "area": {
                "fill": markColor,
            },
            "line": {
                # "color": markColor,
                "stroke": markColor,
                "strokeWidth": 2,
            },
            "trail": {
                "color": markColor,
                "stroke": markColor,
                "strokeWidth": 0,
                "size": 1,
            },
            "path": {
                "stroke": markColor,
                "strokeWidth": 0.5,
            },
            "rect": {
                "fill": markColor,
            },
            "point": {
                "filled": True,
                "shape": "circle",
            },
            "shape": {"stroke": markColor},
            "text": {
                "font": sourceFont,
                "color": markColor,
                "fontSize": 11,
                "align": "center",
                "fontWeight": 400,
                "size": 11,
            },
            "bar": {
                # "size": 40,
                "binSpacing": 2,
                # "continuousBandSize": 30,
                # "discreteBandSize": 30,
                "fill": markColor,
                "stroke": False,
            },
        },
    }


# Let's add in more top-level chart configuratinos
# Need to add more since altair_saver will lose a lot of the theme applied
def preset_chart_config(chart):
    chart = (
        chart.properties(
            width=chart_width,
            height=chart_height,
        )
        .configure(background=backgroundColor, font=font)
        .configure_axis(
            domainColor=axisColor,
            grid=True,
            gridColor=axisColor,
            gridWidth=1,
            labelColor=guideLabelColor,
            labelFont=labelFont,
            labelFontSize=10,
            titleColor=guideTitleColor,
            titleFont=font,
            tickColor=axisColor,
            tickSize=10,
            titleFontSize=12,
            titlePadding=10,
            labelPadding=4,
        )
        .configure_axisBand(grid=False)
        .configure_title(
            font=font,
            fontSize=font_size,
            anchor="middle",
            fontWeight=300,
            offset=20,
        )
        .configure_header(labelFont=labelFont, titleFont=font)
        .configure_legend(
            labelColor=blackTitle,
            labelFont=labelFont,
            labelFontSize=11,
            padding=1,
            symbolSize=30,
            symbolType="square",
            titleColor=blackTitle,
            titleFont=font,
            titleFontSize=14,
            titlePadding=10,
            labelLimit=0,
        )
    )
    return chart


# --------------------------------------------------------------#
# Plotnine
# --------------------------------------------------------------#
def preset_plotnine_config(chart):
    chart = (
        chart
        + theme_538()
        + theme(
            plot_background=element_rect(fill=backgroundColor, color=backgroundColor),
            panel_background=element_rect(fill=backgroundColor, color=backgroundColor),
            panel_grid_major_y=element_line(color=axisColor, linetype="solid", size=1),
            panel_grid_major_x=element_blank(),
            figure_size=(7.0, 4.4),
            title=element_text(
                weight="bold", size=font_size, family=font, color=blackTitle
            ),
            axis_title=element_text(family=labelFont, size=12, color=guideTitleColor),
            axis_text=element_text(
                family=labelFont, size=10, color=guideLabelColor, margin={"r": 4}
            ),
            axis_title_x=element_text(margin={"t": 10}),
            axis_title_y=element_text(margin={"r": 10}),
            legend_title=element_text(
                font=labelFont, size=14, color=blackTitle, margin={"b": 10}
            ),
            legend_text=element_text(
                font=labelFont,
                size=11,
                color=blackTitle,
                margin={"t": 5, "b": 5, "r": 5, "l": 5},
            ),
        )
    )

    return chart
