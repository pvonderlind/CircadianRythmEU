import pandas as pd
from astral.geocoder import database, lookup
import geopandas as gpd
from astral import sun
from geo_utils import get_eu_capitals


def get_sunset_sunrise_data(year: int, eu_gpd,csv_path: str = None) -> pd.DataFrame:
    country_capital = get_eu_capitals()
    dates = pd.date_range(start=f'{year}-01-01', end=f'{year}-12-31').to_pydatetime()
    sun_data = []
    for country_iso_a3, capital in country_capital.items():
        city = lookup(capital, database())
        for d in dates:
            try:
                sunrise = sun.sunrise(observer=city.observer, date=d)
                sunset = sun.sunset(observer=city.observer, date=d)
                sun_data.append([country_iso_a3, capital, d.day, d.month, d.year, sunrise.hour, sunset.hour])
            except ValueError:
                print(f"Could not process day {d}")
    sun_info_df = pd.DataFrame(sun_data, columns=['iso_a3', 'capital', 'day', 'month',
                                                  'year', 'sunrise_UTC', 'sunset_UTC'])
    eu_iso_to_geo = eu_gpd.loc[:, ['iso_a3', 'geometry']]
    sun_data_gpd = gpd.GeoDataFrame(sun_info_df.merge(eu_iso_to_geo, on='iso_a3', how='left').set_index('iso_a3'),
                                    geometry='geometry')
    sun_data_gpd = sun_data_gpd.to_crs(3857)
    if csv_path is not None:
        sun_data_gpd.to_file(csv_path)
    return sun_data_gpd
