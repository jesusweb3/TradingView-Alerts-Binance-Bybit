# src/strategies/simple_strategy.py
import time
from typing import Optional
from src.models.signal import TradingSignal, ActionType
from src.utils.logger import get_logger
from src.config.manager import config_manager
from src.exchanges.exchange_manager import ExchangeManager
from .base_strategy import BaseStrategy
from src.parser.signal_parser import SignalParser

logger = get_logger(__name__)


class SimpleStrategy(BaseStrategy):
    """Простая универсальная торговая стратегия"""

    def __init__(self):
        super().__init__("SimpleStrategy")
        self.parser = SignalParser()
        self.exchange_manager = ExchangeManager()
        self.exchange = self.exchange_manager.get_exchange()
        self.last_action: Optional[ActionType] = None

    def parse_message(self, message: str) -> Optional[TradingSignal]:
        """Парсит сообщение от TradingView"""
        return self.parser.parse(message)

    def should_process_signal(self, signal: TradingSignal) -> bool:
        """
        Проверяет нужно ли обрабатывать сигнал (фильтр дубликатов)

        Логика:
        - Первый сигнал всегда обрабатываем
        - Одинаковые сигналы подряд игнорируем (buy -> buy)
        - Противоположные сигналы обрабатываем (buy -> sell)
        """
        if self.last_action is None:
            # Первый сигнал - всегда обрабатываем
            self.last_action = signal.action
            return True

        if self.last_action == signal.action:
            # Одинаковый сигнал подряд - игнорируем
            logger.info(f"Дублирующий сигнал {signal.action.value} - игнорируется")
            return False

        # Противоположный сигнал - обрабатываем
        self.last_action = signal.action
        return True

    def process_signal(self, signal: TradingSignal) -> bool:
        """
        Обрабатывает торговый сигнал

        Логика:
        1. Проверяем что торговля включена
        2. Получаем символ из конфигурации
        3. Проверяем текущую позицию на бирже
        4. Если позиции нет - открываем новую
        5. Если есть позиция в том же направлении - игнорируем
        6. Если есть позиция в противоположном направлении - разворачиваем
        """
        try:
            # Проверяем что торговля включена
            if not config_manager.is_trading_enabled():
                logger.warning("Торговля отключена в конфигурации")
                return False

            # Получаем символ из конфигурации
            symbol = config_manager.get_trading_symbol()

            # Нормализуем символ для работы с биржей
            normalized_symbol = self.exchange.normalize_symbol(symbol)

            current_position = self.exchange.get_current_position(normalized_symbol)

            # Извлекаем валюту котировки из символа
            quote_currency = self.exchange.extract_quote_currency(symbol)

            # Получаем размер позиции из конфигурации
            position_size = self._get_position_size()

            logger.info(f"Обработка сигнала {signal.action.value} для {symbol}")

            if current_position is None:
                # Позиции нет - открываем новую
                return self._open_new_position(signal, normalized_symbol, position_size, quote_currency)

            # Есть позиция - проверяем направление
            current_side = current_position['side']

            if (signal.is_buy and current_side == "Buy") or (signal.is_sell and current_side == "Sell"):
                # Позиция уже в нужном направлении
                logger.info(f"Позиция {symbol} уже в направлении {signal.action.value} - пропускаем")
                return True

            # Нужно развернуть позицию
            return self._reverse_position(signal, normalized_symbol, position_size, quote_currency)

        except Exception as e:
            logger.error(f"Ошибка обработки сигнала {signal}: {e}")
            return False

    @staticmethod
    def _get_position_size() -> float:
        """Получает размер позиции из конфигурации биржи"""
        try:
            exchange_config = config_manager.get_exchange_config()
            position_size = exchange_config.get('position_size')
            if position_size is None:
                raise ValueError("В config.yaml не найдено обязательное поле exchange.position_size")

            return float(position_size)
        except Exception as e:
            logger.error(f"Критическая ошибка получения размера позиции: {e}")
            raise RuntimeError(f"Не удалось загрузить размер позиции из конфигурации: {e}")

    def _open_new_position(self, signal: TradingSignal, normalized_symbol: str, position_size: float,
                           quote_currency: str) -> bool:
        """Открывает новую позицию"""
        # Проверяем баланс
        balance = self.exchange.get_account_balance(quote_currency)
        if balance < position_size:
            logger.error(f"Недостаточно средств {quote_currency}. Требуется: {position_size}, доступно: {balance}")
            return False

        if signal.is_buy:
            success = self.exchange.open_long_position(normalized_symbol, position_size)
        else:
            success = self.exchange.open_short_position(normalized_symbol, position_size)

        if not success:
            direction = "Long" if signal.is_buy else "Short"
            logger.error(f"Не удалось открыть {direction} позицию {normalized_symbol}")

        return success

    def _reverse_position(self, signal: TradingSignal, normalized_symbol: str, position_size: float,
                          quote_currency: str) -> bool:
        """Разворачивает позицию"""
        logger.info(f"Разворот позиции {normalized_symbol} в {signal.action.value}")

        # Закрываем текущую позицию
        if not self.exchange.close_position(normalized_symbol):
            logger.error(f"Не удалось закрыть текущую позицию {normalized_symbol}")
            return False

        # Небольшая задержка после закрытия
        time.sleep(0.5)

        # Открываем новую позицию в противоположном направлении
        return self._open_new_position(signal, normalized_symbol, position_size, quote_currency)