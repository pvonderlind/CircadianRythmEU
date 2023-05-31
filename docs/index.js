importScripts("https://cdn.jsdelivr.net/pyodide/v0.23.0/full/pyodide.js");

function sendPatch(patch, buffers, msg_id) {
  self.postMessage({
    type: 'patch',
    patch: patch,
    buffers: buffers
  })
}

async function startApplication() {
  console.log("Loading pyodide!");
  self.postMessage({type: 'status', msg: 'Loading pyodide'})
  self.pyodide = await loadPyodide();
  self.pyodide.globals.set("sendPatch", sendPatch);
  console.log("Loaded!");
  await self.pyodide.loadPackage("micropip");
  const env_spec = ['https://cdn.holoviz.org/panel/1.0.3/dist/wheels/bokeh-3.1.1-py3-none-any.whl', 'https://cdn.holoviz.org/panel/1.0.3/dist/wheels/panel-1.0.3-py3-none-any.whl', 'pyodide-http==0.2.1', 'geopandas', 'pandas']
  for (const pkg of env_spec) {
    let pkg_name;
    if (pkg.endsWith('.whl')) {
      pkg_name = pkg.split('/').slice(-1)[0].split('-')[0]
    } else {
      pkg_name = pkg
    }
    self.postMessage({type: 'status', msg: `Installing ${pkg_name}`})
    try {
      await self.pyodide.runPythonAsync(`
        import micropip
        await micropip.install('${pkg}');
      `);
    } catch(e) {
      console.log(e)
      self.postMessage({
	type: 'status',
	msg: `Error while installing ${pkg_name}`
      });
    }
  }
  console.log("Packages loaded!");
  self.postMessage({type: 'status', msg: 'Executing code'})
  const code = `
  
import asyncio

from panel.io.pyodide import init_doc, write_doc

init_doc()

from bokeh.plotting import figure
from bokeh.models import GeoJSONDataSource, LinearColorMapper, ColorBar, ColumnDataSource, LabelSet, HoverTool
from bokeh.tile_providers import Vendors
from bokeh.models import DataTable, TableColumn
from bokeh.palettes import Plasma256
from bokeh.palettes import brewer
import json
import panel as pn
from datetime import date
import geopandas as gpd
import pandas as pd

eu_data_path = 'https://raw.githubusercontent.com/pvonderlind/CircadianRythmEU/master/datasets/saved/eu_gpd.geojson'
city_data_path = 'https://raw.githubusercontent.com/pvonderlind/CircadianRythmEU/master/datasets/saved/city_data.csv'
sunset_data = 'https://raw.githubusercontent.com/pvonderlind/CircadianRythmEU/master/datasets/saved/sunset_data_2022.geojson'

eu_gpd = gpd.read_file(eu_data_path)
top_city_data = pd.read_csv(city_data_path)
sun_data_gpd = gpd.read_file(sunset_data)

data_field = 'sunrise_UTC'
bokeh_tools = 'wheel_zoom, pan, box_zoom, reset'
colorbar_settings = {'title_text_font_size': '12pt', 'label_standoff': 12}


def get_bokeh_geodata_source(gpd_df):
    json_data = json.dumps(json.loads(gpd_df.to_json()))
    return GeoJSONDataSource(geojson=json_data)


def bokeh_plot_map(data):
    p = figure(toolbar_location='right', tools=bokeh_tools, active_scroll="wheel_zoom",
               title="Distance to eastern timezone meridian for large EU cities",
               x_range=(top_city_data['mercantor_x'].min(), top_city_data['mercantor_x'].max()))
    p.title.text_font_size = '20px'
    p.xgrid.grid_line_color = None
    p.ygrid.grid_line_color = None

    # AD MAP TILES ---------------------------------------------------------------------------
    p.add_tile(Vendors.CARTODBPOSITRON_RETINA)

    # ADD GEO STUFF FOR COUNTRIES AS A WHOLE -------------------------------------------------
    geo_data_source = get_bokeh_geodata_source(data)

    values = data[data_field]
    palette = brewer['OrRd'][8]
    palette = palette[::-1]
    # Instantiate LinearColorMapper that linearly maps numbers in a range, into a sequence of colors.
    color_mapper = LinearColorMapper(palette=palette, low=values.min(), high=values.max())
    color_bar = ColorBar(color_mapper=color_mapper, location=(0, 0), title='Sunrise (UTC)', **colorbar_settings)
    country_suntimes = p.patches('xs', 'ys', source=geo_data_source,
                                 fill_color={'field': data_field, 'transform': color_mapper},
                                 line_color='blue',
                                 line_width=0.5,
                                 fill_alpha=0.8)
    p.add_layout(color_bar, 'below')

    # TOOLTIPS FOR COUNTRY PATCHES
    tooltips_country = [
        ('Country', '@iso_a3'),
        ('Sunrise (UTC)', '@sunrise_UTC'),
        ('Sunset (UTC)', '@sunset_UTC')
    ]
    p.add_tools(HoverTool(renderers=[country_suntimes], tooltips=tooltips_country))

    # ===================================================================================================================

    # ADD TIMEZONE INFO PER TOP N CITIES FOR EACH COUNTRY ------------------------------------

    city_data_source = ColumnDataSource(data=top_city_data)
    city_color_mapper = LinearColorMapper(palette=Plasma256,
                                          low=top_city_data['longitudinal_diff_km'].min(),
                                          high=top_city_data['longitudinal_diff_km'].max())
    city_color_bar = ColorBar(color_mapper=city_color_mapper, location=(0, 0),
                              title="Distance to east timezone meridian (Km)", **colorbar_settings)
    city_longdiff_circles = p.circle(x='mercantor_x', y='mercantor_y', source=city_data_source,
                                     color={'field': 'longitudinal_diff_km', 'transform': city_color_mapper}, size=10,
                                     fill_alpha=1)
    labels = LabelSet(x='mercantor_x', y='mercantor_y', x_offset=5, y_offset=5, text='NAME', source=city_data_source,
                      text_color='cornflowerblue')

    p.add_layout(labels)
    p.add_layout(city_color_bar, 'right')

    # TOOLTIPS FOR CITY DATA
    tooltips_city = [
        ('Country', '@country_ISO_A2'),
        ('City', '@NAME'),
        ('Relative position (dist) to timezone border', '@longitudinal_diff_km')
    ]
    p.add_tools(HoverTool(renderers=[city_longdiff_circles], tooltips=tooltips_city, name='test'))
    return p


def bokeh_city_table(city_data):
    source = ColumnDataSource(city_data)
    columns = [
        TableColumn(field="NAME", title="City Name"),
        TableColumn(field="social_timezone", title="Social Timezone"),
        TableColumn(field="longitudinal_diff_km", title="Distance to east meridian (km)"),
        TableColumn(field="country_ISO_A2", title="Country Code (ISO_A2)")
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
    start_date = date(2022,1,1)
    end_date = date(2022,12,31)
    selected_date = pn.widgets.DateSlider(name='Date Slider', value=start_date, start=start_date, end=end_date)
    def update_map(event):
        d = selected_date.value
        selected_sundata = sun_data_gpd.query(f'day == {d.day} & month == {d.month} & year == {d.year}')
        map_pane.object = bokeh_plot_map(selected_sundata)
    selected_date.param.watch(update_map, 'value')
    selected_date.param.trigger('value')

    # CREATE DATATABLES ----------------------------------------------------------------------------------
    sizing_dict = dict(sizing_mode='stretch_both', width_policy='auto', margin=10)
    # Create City Table Panel
    city_data_pane = pn.pane.Bokeh(**sizing_dict)
    city_data_pane.object = bokeh_city_table(top_city_data)

    # Create Sun Table Panel
    sun_data_pane = pn.pane.Bokeh(**sizing_dict)
    sun_data_pane.object = bokeh_sun_table(sun_data_gpd.iloc[:,:-1])

    # Create panel application layout
    map_vis = pn.Column(selected_date, map_pane)
    tabs = pn.Tabs(('Map', map_vis), ('City Data', city_data_pane), ('Sun Data', sun_data_pane))
    return tabs


app = map_visualization()
app.servable()


await write_doc()
  `

  try {
    const [docs_json, render_items, root_ids] = await self.pyodide.runPythonAsync(code)
    self.postMessage({
      type: 'render',
      docs_json: docs_json,
      render_items: render_items,
      root_ids: root_ids
    })
  } catch(e) {
    const traceback = `${e}`
    const tblines = traceback.split('\n')
    self.postMessage({
      type: 'status',
      msg: tblines[tblines.length-2]
    });
    throw e
  }
}

self.onmessage = async (event) => {
  const msg = event.data
  if (msg.type === 'rendered') {
    self.pyodide.runPythonAsync(`
    from panel.io.state import state
    from panel.io.pyodide import _link_docs_worker

    _link_docs_worker(state.curdoc, sendPatch, setter='js')
    `)
  } else if (msg.type === 'patch') {
    self.pyodide.globals.set('patch', msg.patch)
    self.pyodide.runPythonAsync(`
    state.curdoc.apply_json_patch(patch.to_py(), setter='js')
    `)
    self.postMessage({type: 'idle'})
  } else if (msg.type === 'location') {
    self.pyodide.globals.set('location', msg.location)
    self.pyodide.runPythonAsync(`
    import json
    from panel.io.state import state
    from panel.util import edit_readonly
    if state.location:
        loc_data = json.loads(location)
        with edit_readonly(state.location):
            state.location.param.update({
                k: v for k, v in loc_data.items() if k in state.location.param
            })
    `)
  }
}

startApplication()