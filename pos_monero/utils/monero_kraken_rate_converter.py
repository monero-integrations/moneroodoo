from typing import override
import requests

from .monero_exchange_rate_converter import MoneroExchangeRateConverter

class MoneroKrakenRateConverter(MoneroExchangeRateConverter):
    _API_URL: str = "https://api.kraken.com/0/public/Ticker"


    def __init__(self) -> None:
        super().__init__("KRAKEN")

    @override
    def get_exchange_rate(self) -> float:
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
        
