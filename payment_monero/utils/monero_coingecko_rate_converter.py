# -*- coding: utf-8 -*-

import requests

from typing import override, Any

from .monero_exchange_rate_converter import MoneroExchangeRateConverter


class MoneroCoinGeckoConverter(MoneroExchangeRateConverter):

    _API_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    _PARAMS: dict[str, Any] = {
        "ids": "monero",
        "vs_currencies": "usd"
    }

    def __init__(self, max_tries: int = 3) -> None:
        super().__init__('CoinGecko', max_tries)
    
    @override
    def _get_exchange_rate(self) -> float:
        response = requests.get(self._API_URL, params=self._PARAMS, timeout=10)
        response.raise_for_status()
        data = response.json()
        rate = data.get("monero", {}).get("usd")

        if rate is None:
            raise Exception("Could not get exchange rate from CoinGecko API")

        return float(rate)
        