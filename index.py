from bokeh.models import DataTable, TableColumn
import geopandas as gpd
import pandas as pd
from bokeh.plotting import figure
from bokeh.models import GeoJSONDataSource, CategoricalColorMapper, ColorBar, ColumnDataSource, LabelSet, HoverTool
from bokeh.tile_providers import get_provider, Vendors
from bokeh.palettes import brewer
import json
import panel as pn
import numpy as np

eu_data_path = 'https://raw.githubusercontent.com/pvonderlind/CircadianRythmEU/master/datasets/saved/eu_gpd.geojson'
city_data_path = 'https://raw.githubusercontent.com/pvonderlind/CircadianRythmEU/master/datasets/saved/city_data.csv'
sunset_data = 'https://raw.githubusercontent.com/pvonderlind/CircadianRythmEU/master/datasets/saved/sunset_data_2022.geojson'
avg_country_data = 'https://raw.githubusercontent.com/pvonderlind/CircadianRythmEU/master/datasets/saved/avg_country.csv'

eu_gpd = gpd.read_file(eu_data_path)
top_city_data = pd.read_csv(city_data_path)
sun_data_gpd = gpd.read_file(sunset_data)
avg_country_data = pd.read_csv(avg_country_data)

data_field = 'social_timezone'
bokeh_tools = 'wheel_zoom, pan, box_zoom, reset, save'
colorbar_settings = {'title_text_font_size': '12pt', 'label_standoff': 12}


def get_bokeh_geodata_source(gpd_df):
    json_data = json.dumps(json.loads(gpd_df.to_json()))
    return GeoJSONDataSource(geojson=json_data)


def bokeh_plot_map(data):
    p = figure(toolbar_location='right', tools=bokeh_tools, active_scroll="wheel_zoom",
               title="Distance to eastern timezone meridian for large EU cities",
               x_range=(-1.3 * 10 ** 6, 4 * 10 ** 6),
               y_range=(4 * 10 ** 6, 9 * 10 ** 6))
    p.title.text_font_size = '20px'
    p.xgrid.grid_line_color = None
    p.ygrid.grid_line_color = None

    # ADD MAP TILES ---------------------------------------------------------------------------
    p.add_tile(Vendors.CARTODBPOSITRON_RETINA)

    # ADD TIMEZONE LINES

    # ADD GEO STUFF FOR COUNTRIES AS A WHOLE -------------------------------------------------
    geo_data_source = get_bokeh_geodata_source(data)

    values = data[data_field]
    palette = brewer['OrRd'][3]
    palette = palette[::-1]
    color_mapper = CategoricalColorMapper(palette=palette, factors=values.unique().tolist())
    color_bar = ColorBar(color_mapper=color_mapper, location=(0, 0), title='Timezone', **colorbar_settings)
    country_tz = p.patches('xs', 'ys', source=geo_data_source,
                           fill_color={'field': data_field, 'transform': color_mapper},
                           line_color='blue',
                           line_width=0.5,
                           fill_alpha=0.8)
    p.add_layout(color_bar, 'below')

    # TOOLTIPS FOR COUNTRY PATCHES
    tooltips_country = [
        ('Country', '@iso_a2')
    ]
    p.add_tools(HoverTool(renderers=[country_tz], tooltips=tooltips_country))

    # ===================================================================================================================

    # ADD BARS FOR DISTANCE TO EAST MERIDIAN EFFECT
    length_scale = 200000
    bar_data_source = ColumnDataSource(dict(
        x0=data['mercantor_x'],
        y0=data['mercantor_y'],
        x1=data['mercantor_x'] + (length_scale * data['norm_weighted_mean_longdiff']) * np.sign(
            data['weighted_mean_longdiff']),
        y1=data['mercantor_y'],
        long_diff=data['mean_longitudinal_diff_km'],
        weighted_long_diff=data['weighted_mean_longdiff'],
        long_diff_norm=data['norm_weighted_mean_longdiff']
    )
    )
    divider_len = 50000
    divider_data_source = ColumnDataSource(dict(
        x0=data['mercantor_x'],
        y0=data['mercantor_y'] - divider_len / 2,
        x1=data['mercantor_x'],
        y1=data['mercantor_y'] + divider_len / 2,
        text=data['name'],
        text_y=(data['mercantor_y'] + divider_len / 2) + 1000
    ))
    longdiff_quads = p.segment(x0="x0", y0="y0", x1="x1", y1="y1", line_width=5, source=bar_data_source)
    londiff_diviers = p.segment(x0="x0", y0="y0", x1="x1", y1="y1", line_width=2, source=divider_data_source)
    longdiff_label = p.text(x="x0", y="text_y", text="text", source=divider_data_source)

    # TOOLTIPS FOR CITY DATA
    tooltips_longquads = [
        ('Relative distance (km) to timezone border', '@long_diff'),
        ('Weighted (population size) diff. to east timezone border', '@weighted_long_diff'),
        ('Normalized, weighted (population size) effect of distance to east meridian', '@long_diff_norm')
    ]
    p.add_tools(HoverTool(renderers=[longdiff_quads], tooltips=tooltips_longquads, name='long_quads'))
    return p


def bokeh_country_table(country_data):
    country_data_sorted = country_data.sort_values('norm_weighted_mean_longdiff', ascending=False)
    source = ColumnDataSource(country_data_sorted)
    columns = [
        TableColumn(field='name', title='Country Name'),
        TableColumn(field="iso_a2", title="Country Code (ISO_A2)"),
        TableColumn(field="social_timezone", title="Social Timezone"),
        TableColumn(field="norm_weighted_mean_longdiff", title="Normalized weighted effect of dist. to east meridian"),
        TableColumn(field="mean_longitudinal_diff_km", title="Avg. dist. to east meridian (km)"),
        TableColumn(field="pop_est", title="Estimated population")
    ]
    data_table = DataTable(source=source, columns=columns)
    return data_table


def bokeh_sun_table(sun_data):
    source = ColumnDataSource(sun_data)

    # Add data table
    columns = [
        TableColumn(field="iso_a3", title="Country Code (ISO_A3)"),
        TableColumn(field="year", title="Year"),
        TableColumn(field="month", title="Month"),
        TableColumn(field="day", title="Day"),
        TableColumn(field="sunrise_UTC", title="Sunrise (UTC/GMT)"),
        TableColumn(field="sunset_UTC", title="Sunrise (UTC/GMT)")
    ]
    data_table = DataTable(source=source, columns=columns)
    return data_table


def map_visualization():
    # CREATE MAP  ----------------------------------------------------------------------------------
    # Create Map Panel
    map_pane = pn.pane.Bokeh(sizing_mode='scale_both', width_policy='max')
    dst_text = pn.widgets.StaticText(value='Daylight savings time (DST) enabled:')
    dst_toggle = pn.widgets.Switch(name="DST Toggle")

    eu_geo_tz = eu_gpd.merge(avg_country_data)

    def update_map(event):
        eu_geo_tz_filter = eu_geo_tz[eu_geo_tz['dst'] == dst_toggle.value]
        map_pane.object = bokeh_plot_map(eu_geo_tz_filter)

    dst_toggle.param.watch(update_map, 'value')
    dst_toggle.param.trigger('value')

    # CREATE DATATABLES ----------------------------------------------------------------------------------
    sizing_dict = dict(sizing_mode='stretch_both', width_policy='auto', margin=10)
    # Create City Table Panel
    country_data_pane = pn.pane.Bokeh(**sizing_dict)
    country_data_pane.object = bokeh_country_table(avg_country_data)

    # Create Sun Table Panel
    sun_data_pane = pn.pane.Bokeh(**sizing_dict)
    sun_data_pane.object = bokeh_sun_table(sun_data_gpd.iloc[:, :-1])

    # Create panel application layout
    map_vis = pn.Column(pn.Row(dst_text, dst_toggle), map_pane)
    tabs = pn.Tabs(('Map', map_vis), ('Country Data', country_data_pane))
    return tabs


# SERVE APP
app = map_visualization()
app.servable()
