# src/exchanges/exchange_manager.py
from typing import Optional
from src.utils.logger import get_logger
from src.config.manager import config_manager
from .base_exchange import BaseExchange
from .bybit.client import BybitClient
from .binance.client import BinanceClient

logger = get_logger(__name__)


class ExchangeManager:
    """Менеджер для управления биржами"""

    def __init__(self):
        self.active_exchange: Optional[BaseExchange] = None
        self._initialize_exchange()

    def _initialize_exchange(self):
        """Инициализирует активную биржу"""
        exchange_config = config_manager.get_exchange_config()
        active_exchange_name = config_manager.get_active_exchange_name()

        # Инициализируем активную биржу
        if active_exchange_name == 'bybit':
            self._initialize_bybit(exchange_config)
        elif active_exchange_name == 'binance':
            self._initialize_binance(exchange_config)
        else:
            raise ValueError(f"Неподдерживаемая биржа: {active_exchange_name}")

    def _initialize_bybit(self, exchange_config: dict):
        """Инициализирует ByBit биржу"""
        credentials = config_manager.get_exchange_credentials('bybit')

        self.active_exchange = BybitClient(
            api_key=credentials['api_key'],
            secret=credentials['secret'],
            testnet=credentials.get('testnet', False),
            position_size=exchange_config['position_size'],
            leverage=exchange_config['leverage']
        )

        logger.info("Активная биржа: ByBit")

    def _initialize_binance(self, exchange_config: dict):
        """Инициализирует Binance биржу"""
        credentials = config_manager.get_exchange_credentials('binance')

        self.active_exchange = BinanceClient(
            api_key=credentials['api_key'],
            secret=credentials['secret'],
            testnet=credentials.get('testnet', False),
            position_size=exchange_config['position_size'],
            leverage=exchange_config['leverage']
        )

        logger.info("Активная биржа: Binance")

    def get_exchange(self) -> BaseExchange:
        """Возвращает активную биржу"""
        if not self.active_exchange:
            raise RuntimeError("Биржа не инициализирована")

        return self.active_exchange

    def reload_config(self):
        """Перезагружает конфигурацию и пересоздает биржу"""
        config_manager.clear_cache()
        self.active_exchange = None
        self._initialize_exchange()
        logger.info("Конфигурация биржи перезагружена")