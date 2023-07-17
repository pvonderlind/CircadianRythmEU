import datetime
import pandas as pd
from astral import sun, LocationInfo

YEAR = 2022
LAST_SUNDAY_OF_OCTOBER = 30  # At this date wintertime (ST) is activated again
LAST_SUNDAY_OF_MARCH = 27  # At this date summertime (DST) is activated


def get_sunrise_data_avgs_for_countries(top_cities: pd.DataFrame) -> pd.DataFrame:
    dates = pd.date_range(start=f'{YEAR}-01-01', end=f'{YEAR}-12-31').to_pydatetime()
    sun_df = _calculate_sunrise_for_city_df(top_cities, dates)
    avg_sun_df = _calculate_averages_for_countries_for_st_dst(sun_df)
    avg_sun_df = _add_differences_to_9_o_clock(avg_sun_df)
    return avg_sun_df.reset_index()


def _calculate_sunrise_for_city_df(top_cities: pd.DataFrame, dates: list) -> pd.DataFrame:
    """
    :param top_cities: A dataframe where each row contains cities returned by geo_utils.get_eu_city_data
    :param dates: An iterable of pydatetimes to calculate sunrises for each city for.
    :return: Returns a pd.Dataframe containing the sunrise data for each given city in top_cities (e.g. each row).
    """
    sun_data = []
    for idx, row in top_cities.iterrows():
        location = LocationInfo(row['NAME'],
                                row['country_ISO_A2'],
                                row['social_timezone'],
                                row['latitude'],
                                row['longitude'])
        for d in dates:
            try:
                sunrise_utc = sun.sunrise(observer=location.observer, date=d)
                sunrise_converted = _get_all_conversions_for_sunrise_time(sunrise_utc, row['utc_sun_timezone_offset'])
                sun_data.append([row['country_ISO_A2'], row['NAME'], d.day, d.month, d.year,
                                 sunrise_utc.hour, sunrise_utc.minute,  # Sunrise in UTC/GMT
                                 ] + sunrise_converted)
            except ValueError:
                print(f"Could not process day {d}")

    columns = ['country_ISO_A2', 'NAME', 'day', 'month', 'year',
               'sunrise_utc_hour', 'sunrise_minute',
               'sunrise_local_hour', 'sunrise_local_hour_dst']
    sun_df = pd.DataFrame(sun_data, columns=columns)
    sun_df = _add_time_columns_to(sun_df)
    return sun_df


def _get_all_conversions_for_sunrise_time(sunrise_utc: datetime.datetime, city_utc_offset: int) -> list:
    # Sunrise converted to STANDARD TIME OF CITY
    sunrise_local_hour_st = sunrise_utc.hour + city_utc_offset
    # Sunrise converted to DAYLIGHT SAVINGS TIME OF CITY
    sunrise_local_hour_dst = sunrise_local_hour_st + 1
    return [sunrise_local_hour_st, sunrise_local_hour_dst]


def _add_time_columns_to(sun_df: pd.DataFrame) -> pd.DataFrame:
    sun_df['date'] = pd.to_datetime(sun_df[['day', 'month', 'year']]).dt.date
    sun_df['sunrise_local_time'] = sun_df.apply(
        lambda x: datetime.time(hour=x['sunrise_local_hour'], minute=x['sunrise_minute']), axis=1)
    sun_df['sunrise_local_dst_time'] = sun_df.apply(
        lambda x: datetime.time(hour=x['sunrise_local_hour_dst'], minute=x['sunrise_minute']), axis=1)
    return sun_df


def _calculate_averages_for_countries_for_st_dst(sun_df: pd.DataFrame) -> pd.DataFrame:
    sun_df_dst = _calculate_sunrise_averages_for_countries(sun_df, 'sunrise_local_dst_time')
    sun_df_dst['dst'] = True

    sun_df_st = _calculate_sunrise_averages_for_countries(sun_df, 'sunrise_local_time')
    sun_df_st['dst'] = False

    return pd.concat([sun_df_dst, sun_df_st])


def _calculate_sunrise_averages_for_countries(sun_df: pd.DataFrame, time_column: str) -> pd.DataFrame:
    # Averages using both ST (+0h) and DST (+1h) in period of March to October ('Summertime')
    summer_period_start = datetime.date(year=YEAR, month=3, day=LAST_SUNDAY_OF_MARCH)
    summer_period_end = datetime.date(year=YEAR, month=10, day=LAST_SUNDAY_OF_OCTOBER)
    summer_period_mask = (sun_df['date'] > summer_period_start) & (sun_df['date'] < summer_period_end)

    delta_colname = time_column + '_delta'
    sun_df[delta_colname] = pd.to_timedelta(sun_df[time_column].astype('str'))

    local_time_summer = sun_df.loc[summer_period_mask].groupby('country_ISO_A2')[[delta_colname]].mean()

    local_time_winter = sun_df.loc[~summer_period_mask].groupby('country_ISO_A2')[[delta_colname]].mean()

    avg_sunrise_df = pd.concat([local_time_summer, local_time_winter], axis=1)
    avg_sunrise_df.columns = ['summer_period', 'winter_period']
    return avg_sunrise_df


def _add_differences_to_9_o_clock(avg_sun_df: pd.DataFrame) -> pd.DataFrame:
    timestamp_9 = pd.Timedelta(hours=9)
    avg_sun_df['summer_diff_min'] = avg_sun_df['summer_period'].apply(
        lambda x: (timestamp_9 - x).total_seconds() / 60 / 60)
    avg_sun_df['winter_diff_min'] = avg_sun_df['winter_period'].apply(
        lambda x: (timestamp_9 - x).total_seconds() / 60 / 60)
    return avg_sun_df


if __name__ == "__main__":
    test_cities = pd.read_csv('datasets/saved/city_data.csv')
    sun_data = get_sunrise_data_avgs_for_countries(test_cities)
    pass
