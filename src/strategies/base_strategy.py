# src/strategies/base_strategy.py
from abc import ABC, abstractmethod
from typing import Optional
from src.models.signal import TradingSignal


class BaseStrategy(ABC):
    """Базовый класс для всех торговых стратегий"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def parse_message(self, message: str) -> Optional[TradingSignal]:
        """
        Парсит сообщение от TradingView в торговый сигнал

        Args:
            message: Сообщение от TradingView

        Returns:
            TradingSignal если сообщение от этой стратегии, None иначе
        """
        pass

    @abstractmethod
    def should_process_signal(self, signal: TradingSignal) -> bool:
        """
        Проверяет нужно ли обрабатывать этот сигнал (фильтр дубликатов)

        Args:
            signal: Торговый сигнал

        Returns:
            True если сигнал нужно обработать, False если игнорировать
        """
        pass

    @abstractmethod
    def process_signal(self, signal: TradingSignal) -> bool:
        """
        Обрабатывает торговый сигнал (открывает/закрывает позиции)

        Args:
            signal: Торговый сигнал

        Returns:
            True если сигнал обработан успешно, False иначе
        """
        pass