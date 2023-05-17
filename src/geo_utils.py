import geopandas as gpd
from countryinfo import CountryInfo
from unidecode import unidecode


def load_eu_countries_as_geopandas(ignored_countries=None) -> gpd.GeoDataFrame:
    """
    Loads a geopandas dataframe using the 'naturalearth_lowres' dataset from GeoPandas
    for europe. This includes borders and other country data.
    :param ignored_countries: A list of countries in ISO_A3 to ignore.
    :return: Returns a GeoPandas dataframe of EU countries.
    """
    if ignored_countries is None:
        ignored_countries = ['RUS']
    world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
    europe = world[world.continent == 'Europe']
    europe = europe[~europe['iso_a3'].isin(ignored_countries)]
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


def _add_relative_position_in_timezone(countries_df: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Adds the relative position in the respective timezone for each country in the given
    dataframe. Uses the naturalearth 10m-cultural-vectors (Timezones) dataset.

    :param countries_df: GeoPandas dataframe containing at least the geometry, iso_a3 code
    and capital name (normalized with unidecode) of EU countries.
    :return: Returns a GeoPandas dataframe extended by the relative position feature.
    """
    pass
