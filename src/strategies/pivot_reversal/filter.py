# src/strategies/pivot_reversal/filter.py
from typing import Optional
from src.models.signal import TradingSignal, ActionType
from src.logger.config import setup_logger

logger = setup_logger(__name__)


class PivotReversalFilter:
    """Фильтр дубликатов для стратегии контрольной точки разворота"""

    def __init__(self):
        self.last_action: Optional[ActionType] = None

    def should_process(self, signal: TradingSignal) -> bool:
        """
        Проверяет нужно ли обрабатывать сигнал

        Логика:
        - Первый сигнал всегда обрабатываем
        - Одинаковые сигналы подряд игнорируем (buy -> buy)
        - Противоположные сигналы обрабатываем (buy -> sell)

        Args:
            signal: Торговый сигнал

        Returns:
            True если сигнал нужно обработать, False если игнорировать
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