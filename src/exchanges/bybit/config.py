# src/exchanges/bybit/config.py
from dataclasses import dataclass


@dataclass
class BybitConfig:
    """Конфигурация для ByBit биржи"""
    api_key: str
    secret: str
    testnet: bool
    position_size: float
    leverage: int