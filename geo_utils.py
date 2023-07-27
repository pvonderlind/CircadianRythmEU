import geopandas as gpd
import pandas as pd
from countryinfo import CountryInfo
from sklearn.preprocessing import MinMaxScaler
from unidecode import unidecode
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from datetime import datetime
import math

geolocator = Nominatim(user_agent='CircadianRythmEU')
tf = TimezoneFinder()
timezone_df = pd.read_csv('datasets/saved/timezones_eu.csv', index_col=0)
country_whitelist = pd.read_csv('datasets/saved/eu_country_codes.csv')
dt_now = datetime.now()

ADJUST_LOCAL_SUMMERTIME = True
LONGITUDE_DEGREE_KM_RATIO = 80


def load_eu_countries_as_geopandas() -> gpd.GeoDataFrame:
    """
    Loads a geopandas dataframe using the 'naturalearth_lowres' dataset from GeoPandas
    for europe. This includes borders and other country data.
    :param ignored_countries: A list of countries in ISO_A3 to ignore.
    :return: Returns a GeoPandas dataframe of european countries.
    """
    world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
    c = CountryInfo()
    iso_conversion = {v['ISO']['alpha3']: v['ISO']['alpha2'] for _, v in c.all().items()}
    iso_conversion['GRC'] = 'EL' # Hacky solution but this fixes the iso conversion to EU norm
    world['iso_a2'] = world.apply(lambda x: iso_conversion.get(x['iso_a3'], None), axis=1)
    europe = world[world['iso_a2'].isin(country_whitelist['iso_A2'])]
    europe = europe.to_crs(3857)
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
    standard_wintertime_df = _create_averaged_country_df_for_column('longitudinal_diff_km', city_data, eu_data)
    standard_wintertime_df['dst'] = False
    summertime_df = _create_averaged_country_df_for_column('summertime_longitudinal_diff_km', city_data, eu_data)
    summertime_df['dst'] = True

    country_data = pd.concat([standard_wintertime_df, summertime_df])
    # Normalize longdiff AFTER concatenation to get a normalization across DST and standard time.
    pop_sum = country_data[country_data['dst'] == False]['pop_est'].sum()
    scaler = MinMaxScaler()
    country_data['pop_percent'] = country_data['pop_est'] / pop_sum
    country_data['weights'] = scaler.fit_transform(country_data[['pop_norm']])
    country_data['weighted_mean_longdiff'] = country_data['pop_norm'] * country_data['mean_longitudinal_diff_km']
    country_data['norm_weighted_mean_longdiff'] = scaler.fit_transform(country_data[['weighted_mean_longdiff']].abs())
    return country_data


def _create_averaged_country_df_for_column(col_label: str, city_data: pd.DataFrame,
                                           eu_data: pd.DataFrame) -> pd.DataFrame:
    cmeans = city_data.groupby('country_ISO_A2')[col_label].mean()
    country_data = city_data.groupby('country_ISO_A2').first().reset_index()
    country_data['mean_longitudinal_diff_km'] = country_data.apply(lambda x: cmeans[x['country_ISO_A2']], axis=1)
    country_data = country_data[
        ['social_timezone', 'utc_sun_timezone_offset', 'mean_longitudinal_diff_km', 'country_ISO_A2', 'mercantor_x',
         'mercantor_y']]

    # Merge population metric from eu_gpd, normalize and merge to country data
    eu_data_pop = eu_data[['iso_a2', 'pop_est', 'name']]
    scaler = MinMaxScaler()
    eu_data_pop.loc[:, ['pop_norm']] = scaler.fit_transform(eu_data_pop[['pop_est']])
    country_data = country_data.merge(eu_data_pop, left_on='country_ISO_A2', right_on='iso_a2')
    country_data = country_data.drop(columns='country_ISO_A2')
    return country_data


def _get_top_n_pop_cities_per_country(top_n_pop: int) -> pd.DataFrame:
    # Load data from Urban Audit dataset
    eu_cities_pop_full = pd.read_csv('datasets/Eurostat/urban_population/urb_cpop1_page_tabular_full.tsv',
                                     sep='\t', header=0)
    eu_cities_pop_full = eu_cities_pop_full.replace(r'^(\D+)$', 0, regex=True)
    city_codes = pd.read_excel('datasets/Eurostat/urban_population/urb_esms_an4.xlsx', dtype=str)
    city_codes['CODE'] = city_codes['CODE'].apply(lambda x: x.strip())

    # Extract city name, country codes by merging with metadata
    eu_cities_pop = pd.DataFrame()
    eu_cities_pop['code_info'] = eu_cities_pop_full.iloc[:, 0]
    eu_cities_pop['population'] = eu_cities_pop_full.iloc[:, 1:].applymap(
        lambda x: int(x.split(' ')[0]) if type(x) != int else x).astype('int32').max(axis=1)
    eu_cities_pop['CODE'] = eu_cities_pop.iloc[:, 0].apply(lambda x: x.split(',')[-1])
    eu_cities_pop = eu_cities_pop[eu_cities_pop['CODE'].apply(lambda x: x[-1] == 'C')]  # Filter out cities only !
    eu_cities_pop['country_ISO_A2'] = eu_cities_pop['CODE'].apply(lambda x: x[0:2])
    eu_cities_pop = eu_cities_pop[eu_cities_pop['country_ISO_A2'].isin(country_whitelist['iso_A2'])]
    eu_cities = eu_cities_pop.merge(city_codes, on='CODE')
    eu_cities = eu_cities.iloc[:, 1:]

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

    tz_info = timezone_df.loc[x['country_ISO_A2']]
    utc_offset = tz_info['gmt_offset']
    tz_name = tz_info['timezone']

    # Get longitudinal meridian values for each timezone --> 15 degrees per tz (360 deg / 24 hours)
    # We then calculate the distance to it similar to [Trang Vophan et. al 2018]
    standard_winter_time_londiff_km = _get_longdiff_km_for_utc_offset(long, utc_offset)
    summertime_longdiff_km = _get_longdiff_km_for_utc_offset(long, utc_offset + 1)

    return tz_name, utc_offset, summertime_longdiff_km, standard_winter_time_londiff_km


def _get_longdiff_km_for_utc_offset(long, utc_offset: int):
    meridian_east = 15 * utc_offset
    long_diff = meridian_east - long
    long_diff_km = LONGITUDE_DEGREE_KM_RATIO * long_diff
    return long_diff_km


def _get_timezone_data(top_city_data: pd.DataFrame) -> pd.DataFrame:
    # Load timezones and offsets
    tz_geo_info = top_city_data.apply(lambda x: _add_tz_info(x), axis='columns', result_type='expand')
    tz_geo_info.columns = ['social_timezone', 'utc_sun_timezone_offset', 'summertime_longitudinal_diff_km',
                           'longitudinal_diff_km']
    return tz_geo_info


if __name__ == "__main__":
    #test_cities = get_eu_city_data(3)
    eu_data = load_eu_countries_as_geopandas()
    #country_data = get_avg_country_data(test_cities, eu_data)
    pass
