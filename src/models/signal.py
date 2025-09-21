# src/models/signal.py
from enum import Enum
from dataclasses import dataclass


class ActionType(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class TradingSignal:
    action: ActionType

    def __str__(self) -> str:
        return f"Signal: {self.action.value}"

    @property
    def is_buy(self) -> bool:
        return self.action == ActionType.BUY

    @property
    def is_sell(self) -> bool:
        return self.action == ActionType.SELL