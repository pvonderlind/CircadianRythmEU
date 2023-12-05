from bokeh.models import DataTable, TableColumn
import geopandas as gpd
import pandas as pd
from bokeh.plotting import figure
from bokeh.models import GeoJSONDataSource, CategoricalColorMapper, ColorBar, ColumnDataSource, LabelSet, HoverTool
from bokeh.tile_providers import get_provider, Vendors
from bokeh.palettes import brewer
import json
from panel import panel as pn
import numpy as np

eu_geo_tz_path = 'https://raw.githubusercontent.com/pvonderlind/CircadianRythmEU/master/datasets/saved/eu_geo_tz.geojson'
eu_geo_tz = gpd.read_file(eu_geo_tz_path)

data_field = 'social_timezone'
bokeh_tools = 'wheel_zoom, pan, box_zoom, reset, save'
colorbar_settings = {'title_text_font_size': '12pt', 'label_standoff': 12}


def get_bokeh_geodata_source(gpd_df):
    json_data = json.dumps(json.loads(gpd_df.to_json()))
    return GeoJSONDataSource(geojson=json_data)


def bokeh_plot_map(data, winter_period_active: bool):
    p = figure(toolbar_location='right', tools=bokeh_tools, active_scroll="wheel_zoom",
               title="Time difference between sunrise and 9:00 for EU countries",
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

    # ===================================================================================================================

    time_diff_col = data['winter_diff_h' if winter_period_active else 'summer_diff_h']
    avg_sunrise = data['winter_period' if winter_period_active else 'summer_period']
    bar_color = time_diff_col.apply(lambda x: '#ff0000' if np.sign(x) < 0 else 'blue')
    # ADD BARS FOR DISTANCE TO EAST MERIDIAN EFFECT
    length_scale = 100000
    divider_len = 50000
    bar_data_source = ColumnDataSource(dict(
        x0=data['mercantor_x'],
        y0=data['mercantor_y'],
        x1=data['mercantor_x'] + (length_scale * time_diff_col),
        y1=data['mercantor_y'],
        lwd=1 + data['pop_norm'] * 10,
        l_col=bar_color,
        avg_sunrise=avg_sunrise,
        time_diff=time_diff_col,
        country=data['name'],
        pop_percent=data['pop_percent'] * 100,
        long_diff=data['mean_longitudinal_diff_km'],
        weighted_long_diff=data['weighted_mean_longdiff'],
        long_diff_norm=data['norm_weighted_mean_longdiff'],
        text=data['name'],
        text_y=(data['mercantor_y'] + divider_len / 2) + 1000
    )
    )
    divider_data_source = ColumnDataSource(dict(
        x0=data['mercantor_x'],
        y0=data['mercantor_y'] - divider_len / 2,
        x1=data['mercantor_x'],
        y1=data['mercantor_y'] + divider_len / 2,
        l_col=bar_color
    ))
    longdiff_quads = p.segment(x0="x0", y0="y0", x1="x1", y1="y1", line_width="lwd", line_color='l_col',
                               source=bar_data_source)
    londiff_diviers = p.segment(x0="x0", y0="y0", x1="x1", y1="y1", line_width=3, line_color='l_col',
                                source=divider_data_source)
    longdiff_label = p.text(x="x0", y="text_y", text="text", source=bar_data_source)

    # TOOLTIPS FOR CITY DATA
    tooltips_longquads = [
        ('Country', '@country'),
        ('Avg. sunrise', '@avg_sunrise'),
        ('Time difference from sunrise to 9:00', '@time_diff'),
        ('Population percent of EU', '@pop_percent'),
        ('Relative distance (km) to timezone border', '@long_diff'),
        ('Weighted (population size) diff. to east timezone border', '@weighted_long_diff'),
        ('Normalized, weighted (population size) effect of distance to east meridian', '@long_diff_norm')
    ]
    p.add_tools(HoverTool(renderers=[longdiff_label], tooltips=tooltips_longquads, name='long_quads'))
    return p


def bokeh_country_table(country_data):
    country_data_sorted = country_data.sort_values('norm_weighted_mean_longdiff', ascending=False)
    source = ColumnDataSource(country_data_sorted)
    columns = [
        TableColumn(field='name', title='Country Name'),
        TableColumn(field="iso_a2", title="Country Code (ISO_A2)"),
        TableColumn(field="social_timezone", title="Social Timezone"),
        TableColumn(field="pop_est", title="Estimated population"),
        TableColumn(field="pop_percent", title="% of EU population"),
        TableColumn(field="dst", title="DST active"),
        TableColumn(field="summer_period", title="Avg. sunrise in summer period"),
        TableColumn(field="winter_period", title="Avg. sunrise in winter period"),
        TableColumn(field="winter_diff_h", title="Difference between sunrise to 9:00 in winter"),
        TableColumn(field="summer_diff_h", title="Difference between sunrise to 9:00 in summer"),
        TableColumn(field="norm_weighted_mean_longdiff", title="Normalized weighted effect of dist. to east meridian"),
        TableColumn(field="mean_longitudinal_diff_km", title="Avg. dist. to east meridian (km)"),
    ]
    data_table = DataTable(source=source, columns=columns)
    return data_table


def map_visualization():
    # CREATE MAP  ----------------------------------------------------------------------------------
    # Create Map Panel
    map_pane = pn.pane.Bokeh(sizing_mode='scale_both', width_policy='max')
    dst_text = pn.widgets.StaticText(value='Daylight savings time (DST) enabled:')
    dst_toggle = pn.widgets.Switch(name="DST Toggle")

    period_text = pn.widgets.StaticText(
        value='Summer Period (Last Sunday in March) / Winter Period (Last Sunday in October):')
    period_toggle = pn.widgets.Switch(name="Summer/Winter period Toggle")

    filter_df = eu_geo_tz[eu_geo_tz['dst'] == False]
    weighted_time_diff_avg = filter_df.apply(lambda x: x['pop_percent'] * x['summer_diff_h'], axis=1).sum()
    h, m = divmod(weighted_time_diff_avg * 60, 60)
    avg_text = pn.widgets.StaticText(
        value=f'Population weighted avg. time difference from sunrise to 9:00: {int(h)}h:{int(m)}m')

    def update_map(event):
        eu_geo_tz_filter = eu_geo_tz[eu_geo_tz['dst'] == dst_toggle.value]
        map_pane.object = bokeh_plot_map(eu_geo_tz_filter, period_toggle.value)

        new_avg = eu_geo_tz_filter.apply(
            lambda x: x['pop_percent'] * x['winter_diff_h' if period_toggle.value else 'summer_diff_h'], axis=1).sum()
        h, m = divmod(new_avg * 60, 60)
        avg_text.value = f'Population weighted avg. time difference from sunrise to 9:00: {int(h)}h:{int(m)}m'

    dst_toggle.param.watch(update_map, 'value')
    dst_toggle.param.trigger('value')

    period_toggle.param.watch(update_map, 'value')
    period_toggle.param.trigger('value')

    # CREATE DATATABLES ----------------------------------------------------------------------------------
    sizing_dict = dict(sizing_mode='stretch_both', width_policy='auto', margin=10)
    # Create City Table Panel
    country_data_pane = pn.pane.Bokeh(**sizing_dict)
    country_data_pane.object = bokeh_country_table(eu_geo_tz.drop(columns=['geometry']))

    # Create panel application layout
    map_vis = pn.Column(pn.Row(pn.Column(pn.Row(dst_text, dst_toggle), pn.Row(period_text, period_toggle)), avg_text),
                        map_pane)
    tabs = pn.Tabs(('Map', map_vis), ('Country Data', country_data_pane))
    return tabs


# SERVE APP
app = map_visualization()
app.servable()
