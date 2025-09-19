# src/strategies/pivot_reversal/parser.py
import re
from typing import Optional
from src.models.signal import TradingSignal, ActionType
from src.logger.config import setup_logger

logger = setup_logger(__name__)


class PivotReversalParser:
    """Парсер для стратегии контрольной точки разворота"""

    # Паттерн для распознавания стратегии по регулярному выражению
    STRATEGY_PATTERN = r'^Стратегия контрольной точки разворота \(\d+,\s*\d+\):'

    @classmethod
    def can_parse(cls, message: str) -> bool:
        """
        Проверяет может ли этот парсер обработать сообщение

        Args:
            message: Сообщение от TradingView

        Returns:
            True если сообщение от стратегии контрольной точки разворота
        """
        if not message or not isinstance(message, str):
            return False

        return bool(re.match(cls.STRATEGY_PATTERN, message.strip()))

    @classmethod
    def parse(cls, message: str) -> Optional[TradingSignal]:
        """
        Парсит сообщение от TradingView

        Ожидаемый формат:
        "Стратегия контрольной точки разворота (1, 1): ETHUSDT 1 buy"
        "Стратегия контрольной точки разворота (78, 46): ETHUSDT 1 sell"
        "Стратегия контрольной точки разворота (2, 1): ETHUSDC.P 15S sell"

        Returns:
            TradingSignal или None если сообщение не от этой стратегии
        """
        if not cls.can_parse(message):
            return None

        message = message.strip()

        try:
            # Ищем паттерн: "Название стратегии: SYMBOL TIMEFRAME ACTION"
            # Обновленный паттерн поддерживает точку в символе
            pattern = r'^(.+?):\s*([A-Z]+[A-Z0-9.]*)\s+(\w+)\s+(buy|sell)$'
            match = re.match(pattern, message, re.IGNORECASE)

            if not match:
                logger.warning(f"Сообщение от нашей стратегии, но неверный формат: {message}")
                return None

            strategy_name = match.group(1).strip()
            symbol = match.group(2).upper()
            timeframe = match.group(3)
            action_str = match.group(4).lower()

            # Парсим действие
            try:
                action = ActionType(action_str)
            except ValueError:
                logger.error(f"Неизвестное действие: {action_str}")
                return None

            signal = TradingSignal(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                action=action
            )

            # Выводим чистый сигнал как требуется
            logger.info(f"{signal.symbol} {signal.action.value}")
            return signal

        except Exception as e:
            logger.error(f"Ошибка парсинга сообщения '{message}': {e}")
            return None