# src/strategies/strategy_manager.py
from typing import Dict, Optional
from src.logger.config import setup_logger
from src.config.manager import config_manager
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
        strategies_config = config_manager.get_strategies_config()
        active_strategy_name = config_manager.get_active_strategy_name()

        # Создаем экземпляры стратегий для всех названий контрольных точек
        for strategy_name in strategies_config.keys():
            if strategy_name.startswith("Стратегия контрольной точки разворота"):
                self.strategies[strategy_name] = PivotReversalStrategy(strategy_name)

        # Устанавливаем активную стратегию
        if active_strategy_name not in self.strategies:
            raise ValueError(
                f"Стратегия '{active_strategy_name}' не поддерживается. "
                f"Поддерживаются только стратегии контрольной точки разворота."
            )

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

    def reload_config(self):
        """Перезагружает конфигурацию и пересоздает стратегии"""
        config_manager.clear_cache()
        self.strategies.clear()
        self.active_strategy = None
        self._initialize_strategies()
        logger.info("Конфигурация стратегий перезагружена")