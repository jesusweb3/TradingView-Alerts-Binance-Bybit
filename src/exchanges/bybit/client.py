# src/exchanges/bybit/client.py
from pybit.unified_trading import HTTP
from typing import Optional, Dict, Any
from src.logger.config import setup_logger
from ..base_exchange import BaseExchange
from ..retry_handler import retry_on_api_error
from ..quantity_calculator import QuantityCalculator
from .config import BybitConfig


class BybitClient(BaseExchange, QuantityCalculator):
    """Клиент для работы с ByBit биржей"""

    def __init__(self, api_key: str, secret: str, testnet: bool, position_size: float, leverage: int):
        BaseExchange.__init__(self, "ByBit")
        QuantityCalculator.__init__(self, leverage)

        self.config = BybitConfig(api_key, secret, testnet, position_size, leverage)
        self.logger = setup_logger(__name__)

        self.session = HTTP(
            testnet=self.config.testnet,
            api_key=self.config.api_key,
            api_secret=self.config.secret
        )

    def _fetch_instrument_info(self, symbol: str) -> Dict[str, Any]:
        """Получает информацию об инструменте с ByBit API"""
        try:
            response = self.session.get_instruments_info(
                category="linear",
                symbol=symbol
            )

            if response['retCode'] == 0 and response['result']['list']:
                instrument = response['result']['list'][0]

                lot_size_filter = instrument['lotSizeFilter']
                price_filter = instrument['priceFilter']

                info = {
                    'qty_step': float(lot_size_filter['qtyStep']),
                    'min_qty': float(lot_size_filter['minOrderQty']),
                    'max_qty': float(lot_size_filter['maxOrderQty']),
                    'tick_size': float(price_filter['tickSize'])
                }

                # Устанавливаем плечо для этого символа
                self._setup_leverage(symbol)

                return info
            else:
                raise RuntimeError(f"Не удалось получить информацию об инструменте {symbol}")

        except Exception as e:
            self.logger.error(f"Ошибка получения информации об инструменте {symbol}: {e}")
            raise

    def _setup_leverage(self, symbol: str):
        """Устанавливает плечо для символа"""
        try:
            response = self.session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(self.config.leverage),
                sellLeverage=str(self.config.leverage)
            )

            if response['retCode'] == 0:
                self.logger.info(f"Плечо установлено {self.config.leverage}x для {symbol}")
            elif response.get('retCode') == 110043:
                self.logger.info(f"Плечо уже установлено {self.config.leverage}x для {symbol}")
            else:
                self.logger.warning(f"Не удалось установить плечо для {symbol}: {response['retMsg']}")

        except Exception as e:
            if "110043" in str(e):
                self.logger.info(f"Плечо уже установлено {self.config.leverage}x для {symbol}")
            else:
                self.logger.error(f"Ошибка установки плеча для {symbol}: {e}")

    @retry_on_api_error()
    def get_account_balance(self, currency: str) -> float:
        """Получает баланс аккаунта для указанной валюты"""
        response = self.session.get_wallet_balance(accountType="UNIFIED")

        if response['retCode'] == 0:
            for coin in response['result']['list'][0]['coin']:
                if coin['coin'] == currency:
                    return float(coin['walletBalance'])
        return 0.0

    @retry_on_api_error()
    def get_current_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Получает текущую позицию по символу"""
        response = self.session.get_positions(
            category="linear",
            symbol=symbol
        )

        if response['retCode'] == 0 and response['result']['list']:
            position = response['result']['list'][0]
            size = float(position['size'])

            if size > 0:
                return {
                    'side': position['side'],
                    'size': size,
                    'entry_price': float(position['avgPrice']),
                    'unrealized_pnl': float(position['unrealisedPnl'])
                }
        return None

    @retry_on_api_error()
    def get_current_price(self, symbol: str) -> float:
        """Получает текущую цену символа"""
        response = self.session.get_tickers(
            category="linear",
            symbol=symbol
        )

        if response['retCode'] == 0 and response['result']['list']:
            return float(response['result']['list'][0]['lastPrice'])
        return 0.0

    def open_long_position(self, symbol: str, position_size: float) -> bool:
        """Открывает длинную позицию"""
        return self._open_position(symbol, "Buy", position_size)

    def open_short_position(self, symbol: str, position_size: float) -> bool:
        """Открывает короткую позицию"""
        return self._open_position(symbol, "Sell", position_size)

    @retry_on_api_error()
    def _open_position(self, symbol: str, side: str, position_size: float) -> bool:
        """Открывает позицию"""
        current_price = self.get_current_price(symbol)
        if current_price == 0:
            self.logger.error(f"Не удалось получить цену для {symbol}")
            return False

        # Проверяем баланс
        quote_currency = self.extract_quote_currency(symbol)
        balance = self.get_account_balance(quote_currency)
        if balance < position_size:
            self.logger.error(f"Недостаточно средств {quote_currency}. Требуется: {position_size}, доступно: {balance}")
            return False

        # Используем общий метод расчета количества
        quantity = self.calculate_quantity(symbol, position_size, current_price)

        # Валидация количества
        if not self.validate_quantity(quantity, symbol):
            return False

        response = self.session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=str(quantity)
        )

        if response['retCode'] == 0:
            direction = "Long" if side == "Buy" else "Short"
            self.logger.info(f"Открыта {direction} позиция {symbol}: {position_size} по {current_price}")
            return True
        else:
            raise Exception(f"ByBit API ошибка: {response['retMsg']}")

    @retry_on_api_error()
    def close_position(self, symbol: str) -> bool:
        """Закрывает текущую позицию по символу"""
        position = self.get_current_position(symbol)
        if not position:
            return True  # Позиции нет, считаем что закрыто

        opposite_side = "Sell" if position['side'] == "Buy" else "Buy"
        rounded_size = self.round_quantity(position['size'], symbol)

        response = self.session.place_order(
            category="linear",
            symbol=symbol,
            side=opposite_side,
            orderType="Market",
            qty=str(rounded_size),
            reduceOnly=True
        )

        if response['retCode'] == 0:
            self.logger.info(f"Закрыта {position['side']} позиция {symbol}, PnL: {position['unrealized_pnl']}")
            return True
        else:
            raise Exception(f"ByBit API ошибка закрытия позиции: {response['retMsg']}")