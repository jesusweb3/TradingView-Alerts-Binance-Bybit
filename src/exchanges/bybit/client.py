# src/exchanges/bybit/client.py
from pybit.unified_trading import HTTP
from typing import Optional, Dict, Any
from src.logger.config import setup_logger
from ..base_exchange import BaseExchange
from ..retry_handler import retry_on_api_error
from .config import BybitConfig


class BybitClient(BaseExchange):
    """Клиент для работы с ByBit биржей"""

    def __init__(self, api_key: str, secret: str, testnet: bool, position_size: float, leverage: int):
        super().__init__("ByBit")
        self.config = BybitConfig(api_key, secret, testnet, position_size, leverage)
        self.logger = setup_logger(__name__)

        self.session = HTTP(
            testnet=self.config.testnet,
            api_key=self.config.api_key,
            api_secret=self.config.secret
        )

        # Параметры инструментов (заполняются при первом использовании)
        self._instruments_info = {}

    def _get_instrument_info(self, symbol: str):
        """Получает информацию об инструменте"""
        if symbol in self._instruments_info:
            return self._instruments_info[symbol]

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
                    'min_order_qty': float(lot_size_filter['minOrderQty']),
                    'max_order_qty': float(lot_size_filter['maxOrderQty']),
                    'tick_size': float(price_filter['tickSize'])
                }

                self._instruments_info[symbol] = info
                self.logger.info(f"Параметры {symbol}: QtyStep={info['qty_step']}, MinQty={info['min_order_qty']}")

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

    def _round_quantity(self, quantity: float, symbol: str) -> float:
        """Округляет количество в соответствии с требованиями биржи"""
        info = self._get_instrument_info(symbol)
        qty_step = info['qty_step']
        min_qty = info['min_order_qty']
        max_qty = info['max_order_qty']

        precision = len(str(qty_step).split('.')[-1]) if '.' in str(qty_step) else 0
        rounded_qty = round(quantity / qty_step) * qty_step
        rounded_qty = round(rounded_qty, precision)

        if rounded_qty < min_qty:
            rounded_qty = min_qty
        elif rounded_qty > max_qty:
            rounded_qty = max_qty

        return rounded_qty

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

    def _calculate_quantity(self, symbol: str, position_size: float, current_price: float) -> float:
        """Вычисляет количество для торговли"""
        total_value = position_size * self.config.leverage
        raw_quantity = total_value / current_price
        rounded_quantity = self._round_quantity(raw_quantity, symbol)

        self.logger.info(f"Расчет для {symbol}: {total_value} / {current_price} = {rounded_quantity}")
        return rounded_quantity

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

        quantity = self._calculate_quantity(symbol, position_size, current_price)

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
        rounded_size = self._round_quantity(position['size'], symbol)

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