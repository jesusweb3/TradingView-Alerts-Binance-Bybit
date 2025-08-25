# src/strategies/pivot_reversal/strategy.py
from typing import Optional
from src.models.signal import TradingSignal
from src.logger.config import setup_logger
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

    def parse_message(self, message: str) -> Optional[TradingSignal]:
        """Парсит сообщение от TradingView"""
        return self.parser.parse(message)

    def should_process_signal(self, signal: TradingSignal) -> bool:
        """Проверяет нужно ли обрабатывать сигнал"""
        return self.filter.should_process(signal)

    def process_signal(self, signal: TradingSignal) -> bool:
        """
        Обрабатывает торговый сигнал

        Пока что заглушка - просто логируем что сигнал обработан
        В следующих шагах здесь будет реальная торговая логика
        """
        logger.info(f"Обработка сигнала: {signal.symbol} {signal.action.value}")

        # TODO: Здесь будет реальная торговая логика:
        # - Подключение к бирже
        # - Открытие/закрытие позиций
        # - Управление рисками

        return True  # Пока всегда возвращаем успех