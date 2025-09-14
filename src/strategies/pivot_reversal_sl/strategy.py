# src/strategies/pivot_reversal_sl/strategy.py
import time
from typing import Optional
from src.models.signal import TradingSignal
from src.logger.config import setup_logger
from src.exchanges.exchange_manager import ExchangeManager
from src.exchanges.binance.client import BinanceClient
from ..base_strategy import BaseStrategy
from ..pivot_reversal.filter import PivotReversalFilter
from .parser import PivotReversalSLParser
from .position_monitor import PositionMonitor

logger = setup_logger(__name__)


class PivotReversalSLStrategy(BaseStrategy):
    """Стратегия контрольной точки разворота с stop-loss мониторингом"""

    def __init__(self, strategy_name: str):
        super().__init__(strategy_name)
        self.parser = PivotReversalSLParser()
        self.filter = PivotReversalFilter()
        self.exchange_manager = ExchangeManager()
        self.exchange = self.exchange_manager.get_exchange()

        # Инициализируем монитор позиций (приводим к BinanceClient)
        if not isinstance(self.exchange, BinanceClient):
            raise ValueError("PivotReversalSL стратегия поддерживает только Binance")

        self.position_monitor = PositionMonitor(self.exchange)

        logger.info(f"Инициализирована стратегия {strategy_name} с stop-loss мониторингом")

    def parse_message(self, message: str) -> Optional[TradingSignal]:
        """Парсит сообщение от TradingView"""
        return self.parser.parse(message)

    def should_process_signal(self, signal: TradingSignal) -> bool:
        """Проверяет нужно ли обрабатывать сигнал"""
        return self.filter.should_process(signal)

    def process_signal(self, signal: TradingSignal) -> bool:
        """
        Обрабатывает торговый сигнал с учетом stop-loss мониторинга

        Логика:
        1. Если есть активный мониторинг - останавливаем его и отменяем stop-loss
        2. Закрываем текущую позицию если есть
        3. Открываем новую позицию согласно сигналу
        4. Запускаем мониторинг новой позиции
        """
        try:
            symbol = signal.symbol
            logger.info(f"Обработка сигнала: {signal}")

            # Шаг 1: Останавливаем текущий мониторинг если активен
            if self.position_monitor.is_monitoring:
                logger.info("Останавливаем текущий мониторинг позиции")
                self.position_monitor.stop_monitoring()
                # Небольшая пауза для корректного завершения
                time.sleep(1)

            # Шаг 2: Закрываем текущую позицию если есть
            current_position = self.exchange.get_current_position(symbol)
            if current_position:
                logger.info(f"Закрываем текущую позицию: {current_position['side']} {current_position['size']}")
                if not self.exchange.close_position(symbol):
                    logger.error(f"Не удалось закрыть позицию {symbol}")
                    return False
                # Пауза после закрытия позиции
                time.sleep(0.5)

            # Шаг 3: Открываем новую позицию
            position_size = self._get_position_size()
            success = self._open_position_by_signal(signal, symbol, position_size)

            if not success:
                logger.error(f"Не удалось открыть позицию по сигналу {signal}")
                return False

            # Шаг 4: Запускаем мониторинг новой позиции
            logger.info(f"Запускаем мониторинг позиции для {symbol}")
            if not self.position_monitor.start_monitoring(symbol):
                logger.error(f"Не удалось запустить мониторинг для {symbol}")
                # Позиция открыта, но мониторинг не работает - это не критично
                # Продолжаем работу без мониторинга

            return True

        except Exception as e:
            logger.error(f"Ошибка обработки сигнала {signal}: {e}")
            return False

    def _open_position_by_signal(self, signal: TradingSignal, symbol: str, position_size: float) -> bool:
        """
        Открывает позицию согласно сигналу

        Args:
            signal: Торговый сигнал
            symbol: Торговый символ
            position_size: Размер позиции

        Returns:
            True если позиция открыта успешно
        """
        # Проверяем баланс
        quote_currency = self.exchange.extract_quote_currency(symbol)
        balance = self.exchange.get_account_balance(quote_currency)

        if balance < position_size:
            logger.error(f"Недостаточно средств {quote_currency}. "
                         f"Требуется: {position_size}, доступно: {balance}")
            return False

        # Открываем позицию в зависимости от сигнала
        if signal.is_buy:
            success = self.exchange.open_long_position(symbol, position_size)
        else:
            success = self.exchange.open_short_position(symbol, position_size)

        if success:
            direction = "Long" if signal.is_buy else "Short"
            logger.info(f"Открыта {direction} позиция {symbol} размером {position_size}")
        else:
            logger.error(f"Не удалось открыть позицию {symbol}")

        return success

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

    def get_monitoring_status(self) -> dict:
        """
        Возвращает текущий статус мониторинга позиции

        Returns:
            Словарь со статусом мониторинга
        """
        if not self.position_monitor.is_monitoring:
            return {
                "monitoring": False,
                "symbol": None,
                "stop_loss_active": False
            }

        return {
            "monitoring": True,
            "symbol": self.position_monitor.symbol,
            "stop_loss_active": self.position_monitor.has_active_stop_loss(),
            "websocket_connected": self.position_monitor.websocket_manager.is_connected()
        }

    def force_stop_monitoring(self):
        """Принудительно останавливает мониторинг (для отладки/управления)"""
        if self.position_monitor.is_monitoring:
            logger.info("Принудительная остановка мониторинга позиции")
            self.position_monitor.stop_monitoring()
        else:
            logger.info("Мониторинг уже остановлен")

    def cleanup(self):
        """Очищает ресурсы стратегии при завершении"""
        logger.info("Очистка ресурсов стратегии")
        if self.position_monitor.is_monitoring:
            self.position_monitor.stop_monitoring()