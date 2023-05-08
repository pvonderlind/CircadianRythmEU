import pandas as pd
from astral.geocoder import database, lookup
from astral import sun
import os


def get_sunset_sunrise_data(year: int, country_capital: dict[str, str], csv_path: str = None) -> pd.DataFrame:
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
    if csv_path is not None:
        sun_info_df.to_csv(csv_path)
    return sun_info_df
