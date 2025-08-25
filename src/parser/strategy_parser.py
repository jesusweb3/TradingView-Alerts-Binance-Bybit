# src/parser/strategy_parser.py
import re
import yaml
import os
from typing import Optional
from src.models.signal import TradingSignal, ActionType
from src.logger.config import setup_logger

logger = setup_logger(__name__)


class StrategyParser:
    """Универсальный парсер для разных форматов стратегий TradingView"""

    @classmethod
    def load_strategies_config(cls) -> dict:
        """Загружает конфигурацию стратегий из YAML файла"""
        config_path = "config.yaml"

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Файл конфигурации {config_path} не найден")

        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)

            strategies = config.get('strategies', {}).get('available', {})
            if not strategies:
                raise ValueError("В config.yaml не найдена секция strategies.available или она пуста")

            return strategies

        except Exception as e:
            raise ValueError(f"Ошибка загрузки стратегий из config.yaml: {e}")

    @classmethod
    def validate_strategies(cls) -> None:
        """Проверяет что активна ровно одна стратегия"""
        strategies = cls.load_strategies_config()
        active_strategies = [name for name, active in strategies.items() if active]

        if len(active_strategies) == 0:
            raise ValueError("Должна быть активна минимум одна стратегия")
        elif len(active_strategies) > 1:
            raise ValueError(f"Активно больше одной стратегии: {active_strategies}")

        active_strategy = active_strategies[0]
        logger.info(f"Активная стратегия: {active_strategy}")

    @classmethod
    def get_active_strategy(cls) -> str:
        """Возвращает название активной стратегии"""
        strategies = cls.load_strategies_config()
        for name, active in strategies.items():
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
            # Загружаем актуальную конфигурацию стратегий
            strategies = cls.load_strategies_config()

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
            if strategy_name not in strategies:
                logger.warning(f"Неизвестная стратегия: {strategy_name}")
                return None

            # Проверяем что стратегия активна
            if not strategies[strategy_name]:
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