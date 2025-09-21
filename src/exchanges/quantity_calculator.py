# src/exchanges/quantity_calculator.py
from abc import ABC, abstractmethod
from typing import Dict, Any
from src.utils.logger import get_logger

logger = get_logger(__name__)


class QuantityCalculator(ABC):
    """Базовый класс для расчета количества в торговых операциях"""

    def __init__(self, leverage: int):
        self.leverage = leverage
        self._instruments_info: Dict[str, Dict[str, Any]] = {}

    @abstractmethod
    def _fetch_instrument_info(self, symbol: str) -> Dict[str, Any]:
        """
        Получает информацию об инструменте с биржи

        Returns:
            Словарь с параметрами инструмента:
            {
                'qty_step': float,
                'min_qty': float,
                'qty_precision': int (опционально)
            }
        """
        pass

    def get_instrument_info(self, symbol: str) -> Dict[str, Any]:
        """Получает информацию об инструменте с кешированием"""
        if symbol in self._instruments_info:
            return self._instruments_info[symbol]

        info = self._fetch_instrument_info(symbol)
        self._instruments_info[symbol] = info

        logger.info(f"Параметры {symbol}: QtyStep={info.get('qty_step')}, MinQty={info.get('min_qty')}")
        return info

    def calculate_quantity(self, symbol: str, position_size: float, current_price: float) -> float:
        """
        Вычисляет и округляет количество для торговли

        Args:
            symbol: Торговый символ
            position_size: Размер позиции в валюте котировки
            current_price: Текущая цена

        Returns:
            Округленное количество для торговли
        """
        total_value = position_size * self.leverage
        raw_quantity = total_value / current_price
        rounded_quantity = self.round_quantity(raw_quantity, symbol)

        logger.info(f"Расчет для {symbol}: {total_value} / {current_price} = {rounded_quantity}")
        return rounded_quantity

    def round_quantity(self, quantity: float, symbol: str) -> float:
        """
        Округляет количество в соответствии с требованиями биржи

        Args:
            quantity: Исходное количество
            symbol: Торговый символ

        Returns:
            Округленное количество
        """
        info = self.get_instrument_info(symbol)

        qty_step = info.get('qty_step')
        min_qty = info.get('min_qty')
        qty_precision = info.get('qty_precision')

        if qty_step:
            # Округляем по шагу
            precision = len(str(qty_step).split('.')[-1]) if '.' in str(qty_step) else 0
            rounded_qty = round(quantity / qty_step) * qty_step
            rounded_qty = round(rounded_qty, precision)
        elif qty_precision is not None:
            # Округляем по precision
            rounded_qty = round(quantity, qty_precision)
        else:
            # Fallback
            rounded_qty = round(quantity, 3)

        # Применяем минимальное количество
        if min_qty and rounded_qty < min_qty:
            rounded_qty = min_qty

        return rounded_qty

    def validate_quantity(self, quantity: float, symbol: str) -> bool:
        """
        Проверяет что количество соответствует требованиям биржи

        Args:
            quantity: Количество для проверки
            symbol: Торговый символ

        Returns:
            True если количество валидно
        """
        info = self.get_instrument_info(symbol)
        min_qty = info.get('min_qty')
        max_qty = info.get('max_qty')

        if min_qty and quantity < min_qty:
            logger.error(f"Количество {quantity} меньше минимального {min_qty}")
            return False

        if max_qty and quantity > max_qty:
            logger.error(f"Количество {quantity} больше максимального {max_qty}")
            return False

        return True