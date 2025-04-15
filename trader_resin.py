import json
import jsonpickle
import math
import statistics
from typing import Dict, List, Tuple

# Type aliases
Time = int
Symbol = str
Product = str
Position = int
UserId = str
ObservationValue = int

# Constants
RESIN = "RAINFOREST_RESIN"

############################################
# Data model classes
############################################

class Listing:
    def __init__(self, symbol: Symbol, product: Product, denomination: Product):
        self.symbol = symbol
        self.product = product
        self.denomination = denomination

class ConversionObservation:
    def __init__(
        self,
        bidPrice: float,
        askPrice: float,
        transportFees: float,
        exportTariff: float,
        importTariff: float,
        sugarPrice: float,
        sunlightIndex: float
    ):
        self.bidPrice = bidPrice
        self.askPrice = askPrice
        self.transportFees = transportFees
        self.exportTariff = exportTariff
        self.importTariff = importTariff
        self.sugarPrice = sugarPrice
        self.sunlightIndex = sunlightIndex

class Observation:
    def __init__(
        self,
        plainValueObservations: Dict[Product, ObservationValue],
        conversionObservations: Dict[Product, ConversionObservation]
    ) -> None:
        self.plainValueObservations = plainValueObservations
        self.conversionObservations = conversionObservations

    def __str__(self) -> str:
        return "(plainValueObservations: " + jsonpickle.encode(self.plainValueObservations) + ", conversionObservations: " + jsonpickle.encode(self.conversionObservations) + ")"


class Order:
    def __init__(self, symbol: Symbol, price: int, quantity: int) -> None:
        self.symbol = symbol
        self.price = price
        self.quantity = quantity

    def __str__(self) -> str:
        return f"({self.symbol}, {self.price}, {self.quantity})"

    def __repr__(self) -> str:
        return f"({self.symbol}, {self.price}, {self.quantity})"

class OrderDepth:
    def __init__(self):
        self.buy_orders: Dict[int, int] = {}
        self.sell_orders: Dict[int, int] = {}

class Trade:
    def __init__(
        self,
        symbol: Symbol,
        price: int,
        quantity: int,
        buyer: UserId | None = None,
        seller: UserId | None = None,
        timestamp: int = 0
    ) -> None:
        self.symbol = symbol
        self.price: int = price
        self.quantity: int = quantity
        self.buyer = buyer
        self.seller = seller
        self.timestamp = timestamp

    def __str__(self) -> str:
        return f"({self.symbol}, {self.buyer} << {self.seller}, {self.price}, {self.quantity}, {self.timestamp})"

    def __repr__(self) -> str:
        return f"({self.symbol}, {self.buyer} << {self.seller}, {self.price}, {self.quantity}, {self.timestamp})"

class TradingState:
    def __init__(
        self,
        traderData: str,
        timestamp: Time,
        listings: Dict[Symbol, Listing],
        order_depths: Dict[Symbol, OrderDepth],
        own_trades: Dict[Symbol, List[Trade]],
        market_trades: Dict[Symbol, List[Trade]],
        position: Dict[Product, Position],
        observations: Observation
    ):
        self.traderData = traderData
        self.timestamp = timestamp
        self.listings = listings
        self.order_depths = order_depths
        self.own_trades = own_trades
        self.market_trades = market_trades
        self.position = position
        self.observations = observations

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True)

class ProsperityEncoder(json.JSONEncoder):
    def default(self, o):
        return o.__dict__

############################################
# Trader class for Round 1
############################################

class Trader:
    def run(self, state: TradingState):
        """
        1) Maintains a running average price for 'RESIN' across calls using `traderData`.
        2) Performs basic market making with an asymmetric spread if the price is far from the mean.
        3) Respects position limits of ±50 for RESIN.
        """

        ##################################################################
        # 0. UNPACK / INITIALIZE
        ##################################################################

        previous_data = {}
        if state.traderData:
            try:
                previous_data = json.loads(state.traderData)
            except:
                previous_data = {}

        resin_avg_price = previous_data.get("resin_avg_price", 100.0)
        resin_count = previous_data.get("resin_count", 1)

        resin_position = state.position.get(RESIN, 0)

        result = {}

        ##################################################################
        # 1. UPDATE RUNNING PRICE AVERAGE
        ##################################################################

        if RESIN in state.order_depths:
            order_depth = state.order_depths[RESIN]

            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                mid_price = (best_bid + best_ask) / 2.0
            else:
                mid_price = resin_avg_price

            alpha = 0.055  # smoothing factor
            new_avg_price = resin_avg_price * (1 - alpha) + mid_price * alpha
            resin_avg_price = new_avg_price
            resin_count += 1

        ##################################################################
        # 2. DETERMINE FAIR VALUE & ASYMMETRIC SPREAD
        ##################################################################
        if RESIN in state.order_depths:
            order_depth = state.order_depths[RESIN]
            base_spread = 1

            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                current_mid = (best_bid + best_ask) / 2.0
            else:
                current_mid = resin_avg_price

            diff = current_mid - resin_avg_price
            adjust_scale = 0.4
            fair_value = resin_avg_price

            buy_price = fair_value - base_spread / 2
            sell_price = fair_value + base_spread / 2

            if diff > 0:
                sell_price += diff * adjust_scale
                buy_price -= diff * (adjust_scale / 2)
            else:
                buy_price += diff * adjust_scale
                sell_price -= diff * (adjust_scale / 2)

            buy_price = int(round(buy_price))
            sell_price = int(round(sell_price))

            ##################################################################
            # 3. CHECK POSITION LIMITS & FORMULATE ORDERS
            ##################################################################
            orders = []
            current_position = resin_position

            max_order_size = 10
            allowable_buy = 50 - current_position
            allowable_sell = 50 + current_position

            buy_quantity = min(max_order_size, max(0, allowable_buy))
            sell_quantity = min(max_order_size, max(0, allowable_sell))

            if buy_quantity > 0:
                orders.append(Order(RESIN, buy_price, buy_quantity))
            if sell_quantity > 0:
                orders.append(Order(RESIN, sell_price, -sell_quantity))

            result[RESIN] = orders

        ##################################################################
        # 4. SERIALIZE UPDATED STATE
        ##################################################################
        updated_data = {
            "resin_avg_price": resin_avg_price,
            "resin_count": resin_count
        }
        traderData = json.dumps(updated_data)

        ##################################################################
        # 5. (OPTIONAL) CONVERSIONS
        ##################################################################
        conversions = 0

        return result, conversions, traderData

