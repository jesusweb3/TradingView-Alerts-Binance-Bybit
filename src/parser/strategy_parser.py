# src/parser/strategy_parser.py
import re
from typing import Optional
from src.models.signal import TradingSignal, ActionType
from src.logger.config import setup_logger

logger = setup_logger(__name__)


class StrategyParser:
    """Универсальный парсер для разных форматов стратегий TradingView"""

    # Словарь стратегий: название -> активна/неактивна
    STRATEGIES = {
        "Стратегия контрольной точки разворота (1, 1)": True,
        "MACD (12, 26, 9)": False,
    }

    @classmethod
    def validate_strategies(cls) -> None:
        """Проверяет что активна ровно одна стратегия"""
        active_strategies = [name for name, active in cls.STRATEGIES.items() if active]

        if len(active_strategies) == 0:
            raise ValueError("Должна быть активна минимум одна стратегия")
        elif len(active_strategies) > 1:
            raise ValueError(f"Активно больше одной стратегии: {active_strategies}")

        active_strategy = active_strategies[0]
        logger.info(f"Активная стратегия: {active_strategy}")

    @classmethod
    def get_active_strategy(cls) -> str:
        """Возвращает название активной стратегии"""
        for name, active in cls.STRATEGIES.items():
            if active:
                return name
        raise ValueError("Нет активной стратегии")

    @classmethod
    def parse(cls, text_message: str) -> Optional[TradingSignal]:
        """
        Парсит сообщение от TradingView в торговый сигнал

        Поддерживаемые форматы:
        - "Стратегия контрольной точки разворота (1, 1): ETHUSDT 1 buy"
        - "MACD (12, 26, 9): ETHUSDT 1 sell"
        """
        if not text_message or not isinstance(text_message, str):
            logger.warning("Пустое или некорректное сообщение")
            return None

        text_message = text_message.strip()
        logger.info(f"Парсинг сообщения: {text_message}")

        try:
            # Ищем паттерн: "Название стратегии: SYMBOL TIMEFRAME ACTION"
            pattern = r'^(.+?):\s*([A-Z]+[A-Z0-9]*)\s+(\w+)\s+(buy|sell)$'
            match = re.match(pattern, text_message, re.IGNORECASE)

            if not match:
                logger.error(f"Сообщение не соответствует ожидаемому формату: {text_message}")
                return None

            strategy_name = match.group(1).strip()
            symbol = match.group(2).upper()
            timeframe = match.group(3)
            action_str = match.group(4).lower()

            # Проверяем что стратегия известна
            if strategy_name not in cls.STRATEGIES:
                logger.warning(f"Неизвестная стратегия: {strategy_name}")
                return None

            # Проверяем что стратегия активна
            if not cls.STRATEGIES[strategy_name]:
                logger.info(f"Стратегия отключена: {strategy_name}")
                return None

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

            logger.info(f"Сигнал успешно распаршен: {signal}")
            return signal

        except Exception as e:
            logger.error(f"Ошибка парсинга сообщения '{text_message}': {e}")
            return None