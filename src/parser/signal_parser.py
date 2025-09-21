# src/parser/signal_parser.py
from typing import Optional
from src.models.signal import TradingSignal, ActionType
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SignalParser:
    """Простой парсер для стандартных сигналов от TradingView"""

    @staticmethod
    def parse(message: str) -> Optional[TradingSignal]:
        """
        Парсит сообщение от TradingView в торговый сигнал

        Поддерживаемые форматы:
        - "buy"
        - "sell"
        - "BUY"
        - "SELL"
        - Любое сообщение содержащее "buy" или "sell"

        Args:
            message: Сообщение от TradingView

        Returns:
            TradingSignal или None если действие не распознано
        """
        if not message or not isinstance(message, str):
            logger.warning("Пустое или некорректное сообщение")
            return None

        message = message.strip().lower()
        logger.info(f"Парсинг сообщения: {message}")

        try:
            # Ищем "buy" или "sell" в сообщении
            if "buy" in message:
                action = ActionType.BUY
            elif "sell" in message:
                action = ActionType.SELL
            else:
                logger.warning(f"В сообщении '{message}' не найдено действие buy/sell")
                return None

            signal = TradingSignal(action=action)
            logger.info(f"Сигнал успешно распаршен: {signal}")
            return signal

        except Exception as e:
            logger.error(f"Ошибка парсинга сообщения '{message}': {e}")
            return None