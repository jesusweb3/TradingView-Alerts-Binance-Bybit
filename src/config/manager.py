# src/config/manager.py
import yaml
import os
from typing import Dict, Any, Optional
from functools import lru_cache
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ConfigManager:
    """Централизованный менеджер конфигурации с кешированием"""

    _instance: Optional['ConfigManager'] = None
    _config: Optional[Dict[str, Any]] = None

    def __new__(cls) -> 'ConfigManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self._load_config()

    def _load_config(self):
        """Загружает конфигурацию из YAML файла"""
        config_path = "config.yaml"

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Файл конфигурации {config_path} не найден")

        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                self._config = yaml.safe_load(file)
            logger.info("Конфигурация загружена из config.yaml")
        except yaml.YAMLError as e:
            raise ValueError(f"Ошибка парсинга YAML файла: {e}")
        except Exception as e:
            raise ValueError(f"Ошибка загрузки конфигурации: {e}")

    @property
    def config(self) -> Dict[str, Any]:
        """Возвращает полную конфигурацию"""
        if self._config is None:
            self._load_config()
        return self._config

    def reload(self):
        """Перезагружает конфигурацию из файла"""
        self._config = None
        self._load_config()

    @lru_cache(maxsize=1)
    def get_exchange_config(self) -> dict:
        """Возвращает конфигурацию биржи с валидацией"""
        exchange_config = self.config.get('exchange', {})
        if not exchange_config:
            raise ValueError("В config.yaml не найдена секция exchange или она пуста")

        # Валидация обязательных полей
        required_fields = ['position_size', 'leverage']
        for field in required_fields:
            if field not in exchange_config:
                raise ValueError(f"В config.yaml отсутствует обязательное поле exchange.{field}")

        # Валидация активности биржи
        bybit_enabled = exchange_config.get('bybit_enabled', False)
        binance_enabled = exchange_config.get('binance_enabled', False)

        if bybit_enabled and binance_enabled:
            raise ValueError("Только одна биржа может быть активна одновременно")

        if not bybit_enabled and not binance_enabled:
            raise ValueError("Должна быть включена минимум одна биржа")

        return exchange_config

    @lru_cache(maxsize=1)
    def get_trading_config(self) -> dict:
        """Возвращает конфигурацию торговли с валидацией"""
        trading_config = self.config.get('trading', {})
        if not trading_config:
            raise ValueError("В config.yaml не найдена секция trading или она пуста")

        # Валидация обязательных полей
        required_fields = ['enabled', 'symbol']
        for field in required_fields:
            if field not in trading_config:
                raise ValueError(f"В config.yaml отсутствует обязательное поле trading.{field}")

        # Валидация символа
        symbol = trading_config.get('symbol', '')
        if not symbol or not isinstance(symbol, str):
            raise ValueError("В config.yaml поле trading.symbol должно быть непустой строкой")

        return trading_config

    @lru_cache(maxsize=1)
    def get_server_config(self) -> dict:
        """Возвращает конфигурацию сервера с валидацией"""
        server_config = self.config.get('server', {})

        allowed_ips = server_config.get('allowed_ips', [])
        if not allowed_ips:
            raise ValueError("В config.yaml не найдена секция server.allowed_ips или она пуста")

        return server_config

    def get_active_exchange_name(self) -> str:
        """Возвращает название активной биржи"""
        exchange_config = self.get_exchange_config()

        if exchange_config.get('bybit_enabled', False):
            return 'bybit'
        elif exchange_config.get('binance_enabled', False):
            return 'binance'

        raise ValueError("Нет активной биржи")

    def get_trading_symbol(self) -> str:
        """Возвращает торгуемый символ"""
        trading_config = self.get_trading_config()
        return trading_config['symbol']

    def is_trading_enabled(self) -> bool:
        """Возвращает статус включения торговли"""
        trading_config = self.get_trading_config()
        return trading_config.get('enabled', False)

    def get_exchange_credentials(self, exchange_name: str) -> dict:
        """Возвращает учетные данные для указанной биржи с валидацией"""
        exchange_config = self.get_exchange_config()
        credentials = exchange_config.get(exchange_name, {})

        required_fields = ['api_key', 'secret']
        for field in required_fields:
            if not credentials.get(field):
                raise ValueError(f"В config.yaml отсутствует обязательное поле exchange.{exchange_name}.{field}")

        return credentials

    def clear_cache(self):
        """Очищает кеш всех lru_cache методов"""
        self.get_exchange_config.cache_clear()
        self.get_trading_config.cache_clear()
        self.get_server_config.cache_clear()


# Глобальный экземпляр для использования в приложении
config_manager = ConfigManager()