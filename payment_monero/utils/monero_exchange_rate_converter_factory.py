from abc import ABC

from .monero_exchange_rate_converter import MoneroExchangeRateConverter
from .monero_kraken_rate_converter import MoneroKrakenRateConverter
from .monero_coingecko_rate_converter import MoneroCoinGeckoConverter


class MoneroExchangeRateConverterFactory(ABC):

    @classmethod
    def create(cls, api: str) -> MoneroExchangeRateConverter:
        if api == "kraken":
            return MoneroKrakenRateConverter()
        elif api == "coingecko":
            return MoneroCoinGeckoConverter()
        
        raise Exception(f"Unkown exchange rate type '{str(type)}'")
    