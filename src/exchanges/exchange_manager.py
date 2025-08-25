# src/exchanges/exchange_manager.py
import yaml
import os
from typing import Optional
from src.logger.config import setup_logger
from .base_exchange import BaseExchange
from .bybit.client import BybitClient
from .binance.client import BinanceClient

logger = setup_logger(__name__)


class ExchangeManager:
    """Менеджер для управления биржами"""

    def __init__(self):
        self.active_exchange: Optional[BaseExchange] = None
        self._initialize_exchange()

    def _load_exchange_config(self) -> dict:
        """Загружает конфигурацию бирж из YAML файла"""
        config_path = "config.yaml"

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Файл конфигурации {config_path} не найден")

        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)

            exchange_config = config.get('exchange', {})
            if not exchange_config:
                raise ValueError("В config.yaml не найдена секция exchange или она пуста")

            return exchange_config

        except Exception as e:
            raise ValueError(f"Ошибка загрузки конфигурации биржи: {e}")

    def _initialize_exchange(self):
        """Инициализирует активную биржу"""
        config = self._load_exchange_config()

        bybit_enabled = config.get('bybit_enabled', False)
        binance_enabled = config.get('binance_enabled', False)

        # Валидация: только одна биржа может быть активна
        if bybit_enabled and binance_enabled:
            raise ValueError("Только одна биржа может быть активна одновременно")

        if not bybit_enabled and not binance_enabled:
            raise ValueError("Должна быть включена минимум одна биржа")

        # Инициализируем активную биржу
        if bybit_enabled:
            self._initialize_bybit(config)
        elif binance_enabled:
            self._initialize_binance(config)

    def _initialize_bybit(self, config: dict):
        """Инициализирует ByBit биржу"""
        bybit_config = config.get('bybit', {})

        required_fields = ['api_key', 'secret']
        for field in required_fields:
            if not bybit_config.get(field):
                raise ValueError(f"В config.yaml отсутствует обязательное поле exchange.bybit.{field}")

        self.active_exchange = BybitClient(
            api_key=bybit_config['api_key'],
            secret=bybit_config['secret'],
            testnet=bybit_config.get('testnet', False),
            position_size=config.get('position_size', 100.0),
            leverage=config.get('leverage', 10)
        )

        logger.info("Активная биржа: ByBit")

    def _initialize_binance(self, config: dict):
        """Инициализирует Binance биржу"""
        binance_config = config.get('binance', {})

        required_fields = ['api_key', 'secret']
        for field in required_fields:
            if not binance_config.get(field):
                raise ValueError(f"В config.yaml отсутствует обязательное поле exchange.binance.{field}")

        self.active_exchange = BinanceClient(
            api_key=binance_config['api_key'],
            secret=binance_config['secret'],
            testnet=binance_config.get('testnet', False),
            position_size=config.get('position_size', 100.0),
            leverage=config.get('leverage', 10)
        )

        logger.info("Активная биржа: Binance")

    def get_exchange(self) -> BaseExchange:
        """Возвращает активную биржу"""
        if not self.active_exchange:
            raise RuntimeError("Биржа не инициализирована")

        return self.active_exchange