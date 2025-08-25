# src/models/signal.py
from enum import Enum
from dataclasses import dataclass


class ActionType(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class TradingSignal:
    strategy_name: str
    symbol: str
    timeframe: str
    action: ActionType

    def __str__(self) -> str:
        return f"{self.strategy_name}: {self.symbol} {self.timeframe} {self.action.value}"

    @property
    def is_buy(self) -> bool:
        return self.action == ActionType.BUY

    @property
    def is_sell(self) -> bool:
        return self.action == ActionType.SELL