# src/strategies/pivot_reversal/strategy.py
import time
from typing import Optional
from src.models.signal import TradingSignal
from src.logger.config import setup_logger
from src.exchanges.exchange_manager import ExchangeManager
from ..base_strategy import BaseStrategy
from .parser import PivotReversalParser
from .filter import PivotReversalFilter

logger = setup_logger(__name__)


class PivotReversalStrategy(BaseStrategy):
    """Стратегия контрольной точки разворота"""

    def __init__(self):
        super().__init__("Стратегия контрольной точки разворота (1, 1)")
        self.parser = PivotReversalParser()
        self.filter = PivotReversalFilter()
        self.exchange_manager = ExchangeManager()
        self.exchange = self.exchange_manager.get_exchange()

    def parse_message(self, message: str) -> Optional[TradingSignal]:
        """Парсит сообщение от TradingView"""
        return self.parser.parse(message)

    def should_process_signal(self, signal: TradingSignal) -> bool:
        """Проверяет нужно ли обрабатывать сигнал"""
        return self.filter.should_process(signal)

    def process_signal(self, signal: TradingSignal) -> bool:
        """
        Обрабатывает торговый сигнал

        Логика:
        1. Проверяем текущую позицию на бирже
        2. Если позиции нет - открываем новую
        3. Если есть позиция в том же направлении - игнорируем
        4. Если есть позиция в противоположном направлении - разворачиваем
        """
        try:
            symbol = signal.symbol
            current_position = self.exchange.get_current_position(symbol)

            # Извлекаем валюту котировки из символа
            quote_currency = self.exchange.extract_quote_currency(symbol)

            # Получаем размер позиции из конфигурации
            position_size = self._get_position_size()

            if current_position is None:
                # Позиции нет - открываем новую
                return self._open_new_position(signal, symbol, position_size, quote_currency)

            # Есть позиция - проверяем направление
            current_side = current_position['side']

            if (signal.is_buy and current_side == "Buy") or (signal.is_sell and current_side == "Sell"):
                # Позиция уже в нужном направлении
                logger.info(f"Позиция {symbol} уже в направлении {signal.action.value} - пропускаем")
                return True

            # Нужно развернуть позицию
            return self._reverse_position(signal, symbol, position_size, quote_currency)

        except Exception as e:
            logger.error(f"Ошибка обработки сигнала {signal}: {e}")
            return False

    @staticmethod
    def _get_position_size() -> float:
        """Получает размер позиции из конфигурации биржи"""
        import yaml

        try:
            with open("config.yaml", 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)

            position_size = config.get('exchange', {}).get('position_size')
            if position_size is None:
                raise ValueError("В config.yaml не найдено обязательное поле exchange.position_size")

            return float(position_size)
        except Exception as e:
            logger.error(f"Критическая ошибка получения размера позиции: {e}")
            raise RuntimeError(f"Не удалось загрузить размер позиции из конфигурации: {e}")

    def _open_new_position(self, signal: TradingSignal, symbol: str, position_size: float, quote_currency: str) -> bool:
        """Открывает новую позицию"""
        # Проверяем баланс
        balance = self.exchange.get_account_balance(quote_currency)
        if balance < position_size:
            logger.error(f"Недостаточно средств {quote_currency}. Требуется: {position_size}, доступно: {balance}")
            return False

        if signal.is_buy:
            success = self.exchange.open_long_position(symbol, position_size)
        else:
            success = self.exchange.open_short_position(symbol, position_size)

        if not success:
            direction = "Long" if signal.is_buy else "Short"
            logger.error(f"Не удалось открыть {direction} позицию {symbol}")

        return success

    def _reverse_position(self, signal: TradingSignal, symbol: str, position_size: float, quote_currency: str) -> bool:
        """Разворачивает позицию"""
        logger.info(f"Разворот позиции {symbol} в {signal.action.value}")

        # Закрываем текущую позицию
        if not self.exchange.close_position(symbol):
            logger.error(f"Не удалось закрыть текущую позицию {symbol}")
            return False

        # Небольшая задержка после закрытия
        time.sleep(0.5)

        # Открываем новую позицию в противоположном направлении
        return self._open_new_position(signal, symbol, position_size, quote_currency)