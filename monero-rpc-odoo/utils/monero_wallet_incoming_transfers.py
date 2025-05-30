from monero import MoneroIncomingTransfer


class MoneroWalletIncomingTransfers:
    amount: int
    num_confirmations: int
    transfers: list[MoneroIncomingTransfer]

    def __init__(self, transfers: list[MoneroIncomingTransfer]) -> None:
        self.transfers = transfers
        self.amount = 0
        self.num_confirmations = 0

        num_confirmations: int | None = None

        for transfer in transfers:
            if transfer.amount is None:
                continue
            
            self.amount += transfer.amount

            if num_confirmations is None:
                num_confirmations = transfer.tx.num_confirmations
            elif transfer.tx.num_confirmations is not None and transfer.tx.num_confirmations < num_confirmations:
                num_confirmations = transfer.tx.num_confirmations

        if num_confirmations is not None:
            self.num_confirmations = num_confirmations

        if len(transfers) > 0:
            transfer = transfers[0]
