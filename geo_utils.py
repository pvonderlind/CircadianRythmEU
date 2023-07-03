import geopandas as gpd
import numpy as np
import pandas as pd
from countryinfo import CountryInfo
from sklearn.preprocessing import MinMaxScaler
from unidecode import unidecode
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from pytz import timezone
from datetime import datetime
import math

geolocator = Nominatim(user_agent='CircadianRythmEU')
tf = TimezoneFinder()
dt_now = datetime.now()

ADJUST_LOCAL_SUMMERTIME = True
LONGITUDE_DEGREE_KM_RATIO = 80


def load_eu_countries_as_geopandas(ignored_countries=None) -> gpd.GeoDataFrame:
    """
    Loads a geopandas dataframe using the 'naturalearth_lowres' dataset from GeoPandas
    for europe. This includes borders and other country data.
    :param ignored_countries: A list of countries in ISO_A3 to ignore.
    :return: Returns a GeoPandas dataframe of european countries.
    """
    if ignored_countries is None:
        ignored_countries = ['RUS']
    world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
    europe = world[world.continent == 'Europe']
    europe = europe[~europe['iso_a3'].isin(ignored_countries)]
    c = CountryInfo()
    iso_conversion = {v['ISO']['alpha3']: v['ISO']['alpha2'] for _, v in c.all().items()}
    europe['iso_a2'] = europe.apply(lambda x: iso_conversion.get(x['iso_a3'], None), axis=1)
    return europe


def get_eu_capitals() -> dict[str, str]:
    """
    Generates mappings from ISO_A3 country codes to the countries capital city name in normalized fashion.
    :return: Returns a dict mapping from ISO_A3 (key) to capital city name (value).
    """
    europe = load_eu_countries_as_geopandas()
    country = CountryInfo()
    iso_to_cap = {v['ISO']['alpha3']: v['capital'] for k, v in country.all().items() if 'capital' in v.keys()}
    iso_to_cap_EU = {k: v for k, v in iso_to_cap.items() if k in europe['iso_a3'].tolist()}
    iso_to_cap_EU_norm = {k: unidecode(v) for k, v in iso_to_cap_EU.items()}
    return iso_to_cap_EU_norm


def get_eu_city_data(top_n_pop: int = 3) -> pd.DataFrame:
    """
    Loads the top n cities for each EU country using the Urban Audit dataset.
    Enriches the data with timezone features such as the distance to each cities
    assigned sun timezone east meridian.
    :param top_n_pop: n cities to use for each country.
    :return: Returns a dataframe containing city information and timezone features.
    """
    top_n_cities_per_country = _get_top_n_pop_cities_per_country(top_n_pop)
    return _add_timezone_features_to_cities(top_n_cities_per_country)


def get_avg_country_data(city_data: pd.DataFrame, eu_data: pd.DataFrame) -> pd.DataFrame:
    """
    Get average circadian (and other statistical measures) statistics from the top n cities
    for european countries.
    :param city_data: Dataframe of the top n cities population wise for EU countries, has to have country_ISO_A2 field.
    :param eu_data: Dataframe of data related to european countries (stats, geo, etc.), Has to have iso_a2 field.
    :return: Return an dataframe with averages measures of the given cities for each country.
    """
    cmeans = city_data.groupby('country_ISO_A2')['longitudinal_diff_km'].mean()
    country_data = city_data.groupby('country_ISO_A2').first().reset_index()
    country_data['mean_longitudinal_diff_km'] = country_data.apply(lambda x: cmeans[x['country_ISO_A2']], axis=1)
    country_data = country_data[['social_timezone', 'mean_longitudinal_diff_km', 'country_ISO_A2']]

    # Merge population metric from eu_gpd, normalize and merge to country data
    eu_data_pop = eu_data[['iso_a2', 'pop_est', 'name']]
    scaler = MinMaxScaler()
    eu_data_pop.loc[:, ['pop_norm']] = scaler.fit_transform(eu_data_pop[['pop_est']])
    country_data = country_data.merge(eu_data_pop, left_on='country_ISO_A2', right_on='iso_a2')
    country_data['weighted_mean_longdiff'] = country_data['pop_norm'] * country_data['mean_longitudinal_diff_km']
    country_data = country_data.drop(columns='country_ISO_A2')
    return country_data

def _get_top_n_pop_cities_per_country(top_n_pop: int) -> pd.DataFrame:
    # Load data from Urban Audit dataset
    eu_cities_pop = pd.read_csv('datasets/Eurostat/urban_population/urb_cpop1_page_tabular.tsv', sep='\t', header=0)
    city_codes = pd.read_excel('datasets/Eurostat/urban_population/urb_esms_an4.xlsx', dtype=str)

    # Extract city name, country codes by merging with metadata
    eu_cities_pop.columns = ['code_info', 'population']
    eu_cities_pop['population'] = eu_cities_pop['population'].apply(lambda x: int(x.split(' ')[0]))
    eu_cities_pop['CODE'] = eu_cities_pop.iloc[:, 0].apply(lambda x: x.split(',')[-1])
    eu_cities_pop['country_ISO_A2'] = eu_cities_pop['CODE'].apply(lambda x: x[0:2])
    eu_cities = eu_cities_pop.merge(city_codes, on='CODE')
    eu_cities = eu_cities.iloc[:, 1:]
    eu_cities = eu_cities[eu_cities_pop['CODE'].apply(lambda x: len(x) > 2)]

    # Get top n cities population wise per country
    top_n_cities_per_country = eu_cities.groupby('country_ISO_A2').apply(
        lambda x: x.nlargest(top_n_pop, 'population')).reset_index(drop=True)
    return top_n_cities_per_country


def _add_timezone_features_to_cities(top_cities_df: pd.DataFrame) -> pd.DataFrame:
    # Get longitude and latitude, remove NaNs, concat to top cities df on column axis
    geo_city_df = top_cities_df.apply(lambda x: _get_geo_location(x), axis='columns', result_type='expand')
    geo_city_df.columns = ['longitude', 'latitude', 'mercantor_x', 'mercantor_y']
    top_cities_geo = pd.concat([top_cities_df, geo_city_df], axis=1)
    top_cities_geo = top_cities_geo.dropna()
    return pd.concat([top_cities_geo, _get_timezone_data(top_cities_geo)], axis=1)


def _get_geo_location(x):
    city_name = f"{x['NAME']}, {x['country_ISO_A2']}"
    try:
        geo_info = geolocator.geocode(city_name)
        lat = geo_info.latitude
        lon = geo_info.longitude
        merc_x, merc_y = _mercantor_from_coords(lat, lon)
        return lon, lat, merc_x, merc_y
    except AttributeError:
        return None, None, None, None


def _mercantor_from_coords(lat, lon):
    r_major = 6378137.000
    x = r_major * math.radians(lon)
    scale = x / lon
    y = 180 / math.pi * math.log(math.tan(math.pi / 4 + lat * (math.pi / 180) / 2)) * scale
    return x, y


def _add_tz_info(x):
    long = x['longitude']
    lat = x['latitude']
    tz_name = tf.timezone_at(lng=long, lat=lat)
    utc_offset = timezone(tz_name).utcoffset(dt_now, is_dst=True).total_seconds() / 60 / 60

    # Subtract one hour so the timezone of Europe/London is 0 --> All others are fine then too
    # THis works since we are interested in the sun-based timezones only for this
    if ADJUST_LOCAL_SUMMERTIME:
        utc_offset -= 1

    # Get longitudinal meridian values for each timezone --> 15 degrees per tz (360 deg / 24 hours)
    # We then calculate the distance to it similar to [Trang Vophan et. al 2018]
    meridian_east = 15 * utc_offset
    long_diff = meridian_east - long
    long_diff_km = LONGITUDE_DEGREE_KM_RATIO * long_diff

    return tz_name, utc_offset, long_diff, long_diff_km


def _get_timezone_data(top_city_data: pd.DataFrame) -> pd.DataFrame:
    # Load timezones and offsets
    tz_geo_info = top_city_data.apply(lambda x: _add_tz_info(x), axis='columns', result_type='expand')
    tz_geo_info.columns = ['social_timezone', 'utc_sun_timezone_offset', 'longitudinal_diff', 'longitudinal_diff_km']

    # Check if adjustment was correct, if not, maybe look at if summertime is active in you current location
    london_tz = tz_geo_info[tz_geo_info['social_timezone'] == 'Europe/London']
    assert all(london_tz['utc_sun_timezone_offset'] == 0)

    return tz_geo_info
