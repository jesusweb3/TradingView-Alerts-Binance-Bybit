# src/strategies/strategy_manager.py
import yaml
import os
from typing import Dict, Optional
from src.logger.config import setup_logger
from src.models.signal import TradingSignal
from .base_strategy import BaseStrategy
from .pivot_reversal.strategy import PivotReversalStrategy

logger = setup_logger(__name__)


class StrategyManager:
    """Менеджер для управления торговыми стратегиями"""

    def __init__(self):
        self.strategies: Dict[str, BaseStrategy] = {}
        self.active_strategy: Optional[BaseStrategy] = None
        self._initialize_strategies()

    def _initialize_strategies(self):
        """Инициализирует все доступные стратегии"""
        # Регистрируем все известные стратегии
        self.strategies = {
            "Стратегия контрольной точки разворота (1, 1)": PivotReversalStrategy(),
            # Здесь будут добавляться новые стратегии
            # "MACD (12, 26, 9)": MACDStrategy(),
        }

        # Определяем активную стратегию из конфигурации
        self._load_active_strategy()

    def _load_active_strategy(self):
        """Загружает активную стратегию из конфигурации"""
        config_path = "config.yaml"

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Файл конфигурации {config_path} не найден")

        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)

            strategies_config = config.get('strategies', {}).get('available', {})
            if not strategies_config:
                raise ValueError("В config.yaml не найдена секция strategies.available или она пуста")

            # Проверяем что активна ровно одна стратегия
            active_strategies = [name for name, active in strategies_config.items() if active]

            if len(active_strategies) == 0:
                raise ValueError("Должна быть активна минимум одна стратегия")
            elif len(active_strategies) > 1:
                raise ValueError(f"Активно больше одной стратегии: {active_strategies}")

            active_strategy_name = active_strategies[0]

            # Проверяем что стратегия зарегистрирована
            if active_strategy_name not in self.strategies:
                raise ValueError(f"Стратегия '{active_strategy_name}' не зарегистрирована")

            self.active_strategy = self.strategies[active_strategy_name]
            logger.info(f"Активная стратегия: {active_strategy_name}")

        except Exception as e:
            raise ValueError(f"Ошибка загрузки конфигурации стратегий: {e}")

    def process_webhook_message(self, message: str) -> Optional[dict]:
        """
        Обрабатывает сообщение от webhook

        Args:
            message: Сообщение от TradingView

        Returns:
            Словарь с результатом обработки или None если сигнал не обработан
        """
        if not self.active_strategy:
            logger.error("Нет активной стратегии")
            return None

        # Парсим сигнал
        signal = self.active_strategy.parse_message(message)
        if not signal:
            return None

        # Проверяем фильтр дубликатов
        if not self.active_strategy.should_process_signal(signal):
            return {"status": "ignored", "message": "Сигнал отфильтрован как дубликат"}

        # Обрабатываем сигнал
        success = self.active_strategy.process_signal(signal)

        if success:
            return {
                "status": "success",
                "signal": {
                    "strategy": signal.strategy_name,
                    "symbol": signal.symbol,
                    "timeframe": signal.timeframe,
                    "action": signal.action.value
                }
            }
        else:
            return {"status": "error", "message": "Ошибка обработки сигнала"}