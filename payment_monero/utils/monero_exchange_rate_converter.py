# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod


class MoneroExchangeRateConverter(ABC):
    _max_tries: int
    type: str

    def __init__(self, type: str, max_tries: int = 3) -> None:
        self.type = type
        self._max_tries = max_tries

    @abstractmethod
    def _get_exchange_rate(self) -> float:
        raise NotImplementedError("MoneroExchangeRateConverter.usd_to_xmr(): not implemented")

    def get_exchange_rate(self) -> float:
        tries: int = 0
        ex: Exception | None = None

        while tries < self._max_tries:
            try:
                return self._get_exchange_rate()
            except Exception as e:
                if tries == self._max_tries - 1:
                    ex = e                
            finally:
                tries += 1
            
        if ex is not None:
            raise ex
        else:
            raise Exception("Unknow error")

    def usd_to_xmr(self, usd: float) -> float:
        rate = self.get_exchange_rate()

        return usd / rate
