# src/exchanges/binance/config.py
from dataclasses import dataclass


@dataclass
class BinanceConfig:
    """Конфигурация для Binance биржи"""
    api_key: str
    secret: str
    testnet: bool
    position_size: float
    leverage: int