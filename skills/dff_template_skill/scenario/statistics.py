import threading
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)

UPDATE_INTERVAL = 60 * 60 * 12  # 12 hours

GLOBAL_BASE_URL = "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/" \
                  "master/csse_covid_19_data/csse_covid_19_time_series"

DAILY_BASE_URL = "http://raw.githubusercontent.com/CSSEGISandData/COVID-19/" \
                 "master/csse_covid_19_data/csse_covid_19_daily_reports"

GLOBAL_DEATHS_URL = f"{GLOBAL_BASE_URL}/time_series_covid19_deaths_global.csv"
GLOBAL_CONFIRMED_URL = f"{GLOBAL_BASE_URL}/time_series_covid19_confirmed_global.csv"


class CovidFetcher(threading.Thread):
    def __init__(self):
        super().__init__()
        self.data = None
        self.state_data = None  # dict[state, (confirmed, deaths)]
        self.county_data = None  # dict[(state, county), (confirmed, deaths)]
        self.country_data = None  # dict[country, (confirmed, deaths)]

    def run(self) -> None:
        while True:
            curr_data = None

            today = datetime.now().strftime("%m-%d-%Y")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%m-%d-%Y")
            two_days_ago = (datetime.now() - timedelta(days=2)).strftime("%m-%d-%Y")

            for date in [today, yesterday, two_days_ago]:
                try:
                    curr_data = pd.read_csv(f"{DAILY_BASE_URL}/{date}.csv", error_bad_lines=False)
                    logging.info(f"Data for {date} retrieved successfully")
                    break
                except Exception:
                    logging.info(f"Failed to retrieve data for {date}. Trying to retrieve for the day before.")

            if curr_data is None:
                raise Exception("Daily data cannot be retrieved")

            curr_data = curr_data[curr_data["Country_Region"] == "US"]
            state_data = defaultdict(lambda: (0, 0))  # dict[state, (confirmed, deaths)]
            county_data = defaultdict(lambda: (0, 0))  # dict[(state, county), (confirmed, deaths)]
            country_data = defaultdict(lambda: (0, 0))  # dict[country, (confirmed, deaths)]

            for i in curr_data.index:
                state = curr_data["Province_State"][i].lower()
                deaths = curr_data["Deaths"][i]
                confirmed = curr_data["Confirmed"][i]
                state_data[state] = (state_data[state][0] + confirmed, state_data[state][1] + deaths)

                try:
                    county = curr_data["Admin2"][i].lower() + " county"
                    county_data[(state, county)] = (confirmed, deaths)

                except Exception:
                    pass

                global_confirmed = pd.read_csv(GLOBAL_CONFIRMED_URL, error_bad_lines=False)
                global_deaths = pd.read_csv(GLOBAL_DEATHS_URL, error_bad_lines=False)
                global_confirmed = global_confirmed.groupby("Country/Region").sum()
                global_deaths = global_deaths.groupby("Country/Region").sum()

                for country in global_confirmed.index:
                    confirmed = global_confirmed[global_confirmed.columns[-1]][country]
                    deaths = global_deaths[global_deaths.columns[-1]][country]
                    country_data[country.lower()] = (confirmed, deaths)

                self.country_data = country_data
                self.state_data = state_data
                self.county_data = county_data
        
                time.sleep(UPDATE_INTERVAL)


@dataclass(frozen=True)
class CovidData:
    confirmed: int = 0
    deaths: int = 0


class DataHandler:
    def __init__(self, fetcher: CovidFetcher):
        self.fetcher = fetcher
        self.fetcher.start()

    def state(self, state: str) -> CovidData:
        data = self.fetcher.state_data[state.lower()]
        return CovidData(data[0], data[1])

    def county(self, state: str, county: str) -> CovidData:
        data = self.fetcher.county_data[(state.lower(), county.lower())]
        return CovidData(data[0], data[1])

    def country(self, country: str) -> CovidData:
        data = self.fetcher.country_data[country.lower()]
        return CovidData(data[0], data[1])