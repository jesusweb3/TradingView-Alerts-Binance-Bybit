# src/strategies/strategy_manager.py
from typing import Optional
from src.logger.config import setup_logger
from src.config.manager import config_manager
from .base_strategy import BaseStrategy
from .pivot_reversal.strategy import PivotReversalStrategy
from .pivot_reversal_sl.strategy import PivotReversalSLStrategy

logger = setup_logger(__name__)


class StrategyManager:
    """Менеджер для управления торговыми стратегиями"""

    def __init__(self):
        self.active_strategy: Optional[BaseStrategy] = None
        self._initialize_strategies()

    def _initialize_strategies(self):
        """Инициализирует активную стратегию на основе config.yaml"""
        active_strategy_name = config_manager.get_active_strategy_name()

        # Создаем только активную стратегию
        if active_strategy_name.startswith("Стратегия контрольной точки разворота SL"):
            # Стратегия с stop-loss мониторингом
            self.active_strategy = PivotReversalSLStrategy(active_strategy_name)
        elif active_strategy_name.startswith("Стратегия контрольной точки разворота"):
            # Обычная стратегия pivot_reversal
            self.active_strategy = PivotReversalStrategy(active_strategy_name)
        else:
            raise ValueError(f"Неподдерживаемая стратегия: {active_strategy_name}")

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

        logger.info(f"Обработка webhook: {message}")
        logger.info(f"Активная стратегия: {self.active_strategy.name}")

        # Парсим сигнал
        signal = self.active_strategy.parse_message(message)
        logger.info(f"Результат парсинга: {signal}")

        if not signal:
            logger.info("Сигнал не распознан парсером")
            return None

        # Проверяем что сигнал от активной стратегии
        if signal.strategy_name != self.active_strategy.name:
            logger.info(f"Сигнал от неактивной стратегии: {signal.strategy_name} != {self.active_strategy.name}")
            return None

        # Проверяем фильтр дубликатов
        if not self.active_strategy.should_process_signal(signal):
            logger.info("Сигнал отфильтрован как дубликат")
            return {"status": "ignored", "message": "Сигнал отфильтрован как дубликат"}

        # Обрабатываем сигнал
        logger.info("Обрабатываем сигнал...")
        success = self.active_strategy.process_signal(signal)

        if success:
            result = {
                "status": "success",
                "signal": {
                    "strategy": signal.strategy_name,
                    "symbol": signal.symbol,
                    "timeframe": signal.timeframe,
                    "action": signal.action.value
                }
            }

            # Добавляем информацию о мониторинге для SL стратегий
            if hasattr(self.active_strategy, 'get_monitoring_status'):
                result["monitoring"] = self.active_strategy.get_monitoring_status()

            logger.info(f"Сигнал успешно обработан: {result}")
            return result
        else:
            logger.error("Ошибка при обработке сигнала")
            return {"status": "error", "message": "Ошибка обработки сигнала"}

    def get_strategy_status(self) -> dict:
        """
        Возвращает статус текущей стратегии

        Returns:
            Словарь со статусом стратегии
        """
        if not self.active_strategy:
            return {"error": "Нет активной стратегии"}

        status = {
            "strategy_name": self.active_strategy.name,
            "strategy_type": type(self.active_strategy).__name__
        }

        # Добавляем статус мониторинга для SL стратегий
        if hasattr(self.active_strategy, 'get_monitoring_status'):
            status["monitoring"] = self.active_strategy.get_monitoring_status()

        return status

    def reload_config(self):
        """Перезагружает конфигурацию и пересоздает стратегию"""
        # Очищаем ресурсы текущей стратегии
        if self.active_strategy and hasattr(self.active_strategy, 'cleanup'):
            self.active_strategy.cleanup()

        config_manager.clear_cache()
        self.active_strategy = None
        self._initialize_strategies()
        logger.info("Конфигурация стратегий перезагружена")

    def cleanup(self):
        """Очищает ресурсы стратегии"""
        logger.info("Очистка ресурсов StrategyManager")
        if self.active_strategy and hasattr(self.active_strategy, 'cleanup'):
            self.active_strategy.cleanup()