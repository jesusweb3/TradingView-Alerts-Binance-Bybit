# src/parser/strategy_parser.py
import re
from typing import Optional
from src.models.signal import TradingSignal, ActionType
from src.logger.config import setup_logger
from src.config.manager import config_manager

logger = setup_logger(__name__)


class StrategyParser:
    """Универсальный парсер для разных форматов стратегий TradingView"""

    def __init__(self):
        self._active_strategy_name = None
        self._strategies_config = None
        self._load_strategy_config()

    def _load_strategy_config(self):
        """Загружает и кеширует конфигурацию стратегий"""
        self._strategies_config = config_manager.get_strategies_config()
        self._active_strategy_name = config_manager.get_active_strategy_name()
        logger.info(f"Активная стратегия: {self._active_strategy_name}")

    def _is_message_from_active_strategy(self, message: str) -> bool:
        """
        Быстрая проверка принадлежности сообщения к активной стратегии

        Args:
            message: Сообщение от TradingView

        Returns:
            True если сообщение от активной стратегии
        """
        if not message or not isinstance(message, str):
            return False

        message = message.strip()

        # Извлекаем название стратегии из сообщения (до двоеточия)
        colon_pos = message.find(':')
        if colon_pos == -1:
            return False

        strategy_name_from_message = message[:colon_pos].strip()

        # Проверяем точное совпадение с активной стратегией
        return strategy_name_from_message == self._active_strategy_name

    def parse(self, text_message: str) -> Optional[TradingSignal]:
        """
        Парсит сообщение от TradingView в торговый сигнал

        Оптимизированная версия:
        1. Сначала проверяем активность стратегии (быстро)
        2. Только потом делаем детальный парсинг (медленно)

        Поддерживаемые форматы:
        - "Стратегия контрольной точки разворота (1, 1): ETHUSDT 1 buy"
        - "MACD (12, 26, 9): ETHUSDT 1 sell"
        """
        if not text_message or not isinstance(text_message, str):
            logger.warning("Пустое или некорректное сообщение")
            return None

        text_message = text_message.strip()
        logger.info(f"Парсинг сообщения: {text_message}")

        # ОПТИМИЗАЦИЯ: Сначала быстро проверяем активность стратегии
        if not self._is_message_from_active_strategy(text_message):
            logger.info("Сообщение не от активной стратегии - пропускаем парсинг")
            return None

        try:
            # Теперь делаем детальный парсинг только для активной стратегии
            return self._parse_message_details(text_message)

        except Exception as e:
            logger.error(f"Ошибка парсинга сообщения '{text_message}': {e}")
            return None

    def _parse_message_details(self, message: str) -> Optional[TradingSignal]:
        """
        Детальный парсинг сообщения

        Args:
            message: Сообщение от TradingView (уже проверено на активность)

        Returns:
            TradingSignal или None если формат неверный
        """
        # Ищем паттерн: "Название стратегии: SYMBOL TIMEFRAME ACTION"
        pattern = r'^(.+?):\s*([A-Z]+[A-Z0-9]*)\s+(\w+)\s+(buy|sell)$'
        match = re.match(pattern, message, re.IGNORECASE)

        if not match:
            logger.error(f"Сообщение не соответствует ожидаемому формату: {message}")
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

        # Дополнительная проверка что стратегия действительно активна
        if not self._strategies_config.get(strategy_name, False):
            logger.warning(f"Стратегия не активна: {strategy_name}")
            return None

        signal = TradingSignal(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            action=action
        )

        logger.info(f"Сигнал успешно распаршен: {signal}")
        return signal

    def reload_config(self):
        """Перезагружает конфигурацию стратегий"""
        config_manager.clear_cache()
        self._load_strategy_config()
        logger.info("Конфигурация стратегий перезагружена")

    @classmethod
    def validate_strategies(cls) -> None:
        """Проверяет что активна ровно одна стратегия"""
        try:
            config_manager.get_strategies_config()
            active_strategy = config_manager.get_active_strategy_name()
            logger.info(f"Валидация пройдена. Активная стратегия: {active_strategy}")
        except ValueError as e:
            logger.error(f"Ошибка валидации стратегий: {e}")
            raise