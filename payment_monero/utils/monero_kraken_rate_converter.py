# -*- coding: utf-8 -*-
import requests

from typing import override
from datetime import datetime, timedelta, UTC

from .monero_exchange_rate_converter import MoneroExchangeRateConverter


class MoneroKrakenRateConverter(MoneroExchangeRateConverter):
    _API_URL: str = "https://api.kraken.com/0/public/Ticker"
    _CACHE_DURATION_MINUTES: int = 5
    _last_rate: float | None
    _last_update_time: datetime | None

    def __init__(self, cacheDurationMinutes: int = 5) -> None:
        super().__init__("KRAKEN")
        self._CACHE_DURATION_MINUTES = cacheDurationMinutes
        self._last_rate: float | None = None
        self._last_update_time: datetime | None = None

    @override
    def _get_exchange_rate(self) -> float:
        now = datetime.now(UTC)

        if (
            self._last_rate is not None
            and self._last_update_time is not None
            and now - self._last_update_time < timedelta(minutes=self._CACHE_DURATION_MINUTES)
        ):
            return self._last_rate

        try:
            response = requests.get(self._API_URL, params={ "pair": "XMRUSD" })
            response.raise_for_status()
            json_data = response.json()
            result = json_data["result"]
            key = next(iter(result))
            last_trade_price = float(result[key]["c"][0])  # prezzo corrente
            return float(last_trade_price)
        
        except Exception as e:
            raise Exception("Could not get exchange rates from kraken API")
        
