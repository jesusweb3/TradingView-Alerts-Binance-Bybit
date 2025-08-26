# src/strategies/strategy_manager.py
import yaml
import os
from typing import Dict, Optional
from src.logger.config import setup_logger
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
        """Инициализирует стратегии на основе config.yaml"""
        config = self._load_config()

        strategies_config = config.get('strategies', {}).get('available', {})
        if not strategies_config:
            raise ValueError("В config.yaml не найдена секция strategies.available или она пуста")

        # Создаем экземпляр стратегии pivot_reversal для всех названий контрольных точек
        for strategy_name, is_active in strategies_config.items():
            if strategy_name.startswith("Стратегия контрольной точки разворота"):
                self.strategies[strategy_name] = PivotReversalStrategy(strategy_name)

        # Определяем активную стратегию
        self._set_active_strategy(strategies_config)

    @staticmethod
    def _load_config() -> dict:
        """Загружает конфигурацию из YAML файла"""
        config_path = "config.yaml"

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Файл конфигурации {config_path} не найден")

        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
        except Exception as e:
            raise ValueError(f"Ошибка загрузки конфигурации стратегий: {e}")

    def _set_active_strategy(self, strategies_config: dict):
        """Определяет активную стратегию"""
        active_strategies = [name for name, active in strategies_config.items() if active]

        if len(active_strategies) == 0:
            raise ValueError("Должна быть активна минимум одна стратегия")
        elif len(active_strategies) > 1:
            raise ValueError(f"Активно больше одной стратегии: {active_strategies}")

        active_strategy_name = active_strategies[0]

        if active_strategy_name not in self.strategies:
            raise ValueError(
                f"Стратегия '{active_strategy_name}' не поддерживается. Поддерживаются только стратегии контрольной точки разворота.")

        self.active_strategy = self.strategies[active_strategy_name]
        logger.info(f"Активная стратегия: {active_strategy_name}")

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

        # Проверяем что сигнал от активной стратегии
        if signal.strategy_name != self.active_strategy.name:
            logger.info(f"Сигнал от неактивной стратегии: {signal.strategy_name}")
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