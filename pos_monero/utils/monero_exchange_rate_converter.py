

class MoneroExchangeRateConverter:
    type: str

    def __init__(self, type: str) -> None:
        self.type = type

    def get_exchange_rate(self) -> float:
        raise NotImplementedError("MoneroExchangeRateConverter.usd_to_xmr(): not implemented")

    def usd_to_xmr(self, usd: float) -> float:
        rate = self.get_exchange_rate()

        return usd / rate
    
