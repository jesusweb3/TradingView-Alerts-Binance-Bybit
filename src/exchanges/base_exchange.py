# src/exchanges/base_exchange.py
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class BaseExchange(ABC):
    """Базовый класс для работы с биржами"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def get_account_balance(self, currency: str) -> float:
        """
        Получает баланс аккаунта для указанной валюты

        Args:
            currency: Валюта (например, 'USDT', 'USDC')

        Returns:
            Баланс в указанной валюте
        """
        pass

    @abstractmethod
    def get_current_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Получает текущую позицию по символу

        Args:
            symbol: Торговый символ (например, 'ETHUSDT')

        Returns:
            Словарь с информацией о позиции или None если позиции нет
            {
                'side': 'Buy' | 'Sell',
                'size': float,
                'entry_price': float,
                'unrealized_pnl': float
            }
        """
        pass

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        """
        Получает текущую цену символа

        Args:
            symbol: Торговый символ (например, 'ETHUSDT')

        Returns:
            Текущая цена
        """
        pass

    @abstractmethod
    def open_long_position(self, symbol: str, position_size: float) -> bool:
        """
        Открывает длинную позицию

        Args:
            symbol: Торговый символ (например, 'ETHUSDT')
            position_size: Размер позиции в валюте котировки

        Returns:
            True если позиция открыта успешно, False иначе
        """
        pass

    @abstractmethod
    def open_short_position(self, symbol: str, position_size: float) -> bool:
        """
        Открывает короткую позицию

        Args:
            symbol: Торговый символ (например, 'ETHUSDT')
            position_size: Размер позиции в валюте котировки

        Returns:
            True если позиция открыта успешно, False иначе
        """
        pass

    @abstractmethod
    def close_position(self, symbol: str) -> bool:
        """
        Закрывает текущую позицию по символу

        Args:
            symbol: Торговый символ (например, 'ETHUSDT')

        Returns:
            True если позиция закрыта успешно, False иначе
        """
        pass

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """
        Нормализует торговый символ для совместимости с биржей

        Args:
            symbol: Торговый символ (например, 'ETHUSDT', 'ETHUSDC.P')

        Returns:
            Нормализованный символ без суффикса .P
        """
        return symbol.rstrip('.P') if symbol.endswith('.P') else symbol

    @staticmethod
    def extract_quote_currency(symbol: str) -> str:
        """
        Извлекает валюту котировки из торгового символа

        Args:
            symbol: Торговый символ (например, 'ETHUSDT', 'ETHUSDC.P')

        Returns:
            Валюта котировки ('USDT', 'USDC', etc.)
        """
        # Убираем суффикс .P если есть
        clean_symbol = BaseExchange.normalize_symbol(symbol)

        # Применяем стандартную логику к очищенному символу
        if clean_symbol.endswith('USDT'):
            return 'USDT'
        elif clean_symbol.endswith('USDC'):
            return 'USDC'
        elif clean_symbol.endswith('BUSD'):
            return 'BUSD'
        else:
            # Fallback: берем последние 4 символа
            return clean_symbol[-4:] if len(clean_symbol) > 4 else clean_symbol