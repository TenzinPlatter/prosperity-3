import json
import jsonpickle
import math
import statistics
import numpy as np
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
KELP = "KELP"

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
        ##################################################################
        # 0. UNPACK / INITIALIZE STATE
        ##################################################################
        previous_data = {}
        if state.traderData:
            try:
                previous_data = json.loads(state.traderData)
            except Exception:
                previous_data = {}

        # Retrieve persisted state values for the EMA and tick counter.
        kelp_count     = previous_data.get("kelp_count", 0)
        kelp_avg_price = previous_data.get("kelp_avg_price", 0.0)
        kelp_position  = state.position.get(KELP, 0)

        result = {}

        ##################################################################
        # 1. INITIAL SEEDING OF EMA (FIRST TICK ONLY)
        ##################################################################
        if KELP in state.order_depths and kelp_count == 0:
            order_depth = state.order_depths[KELP]
            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                # Seed the EMA with the first available mid–price.
                mid_price = (best_bid + best_ask) / 2.0
                kelp_avg_price = mid_price

        ##################################################################
        # 2. UPDATE EMA USING EXPONENTIAL SMOOTHING
        ##################################################################
        if KELP in state.order_depths:
            order_depth = state.order_depths[KELP]
            # Get the current mid–price
            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                mid_price = (best_bid + best_ask) / 2.0
            else:
                mid_price = kelp_avg_price

            # Use a higher smoothing factor (alpha) during the first 20 ticks (faster adaptation),
            # then a lower alpha subsequently.
            if kelp_count < 20:
                alpha = 0.2
            else:
                alpha = 0.055

            # Exponential moving average update:
            kelp_avg_price = kelp_avg_price * (1 - alpha) + mid_price * alpha
            kelp_count += 1

        ##################################################################
        # 3. MEAN REVERSION SIGNAL: COMPARE CURRENT PRICE TO EMA
        ##################################################################
        # Get the current market mid–price.
        if KELP in state.order_depths:
            order_depth = state.order_depths[KELP]
            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                current_mid = (best_bid + best_ask) / 2.0
            else:
                current_mid = kelp_avg_price
        else:
            current_mid = kelp_avg_price

        # Define a deviation threshold for entering a trade.
        # For example, if the current price is more than 0.7 above/below the EMA.
        deviation_threshold = 0.7

        # Determine signal:
        # - If current price is significantly above the EMA, signal = -1 (sell).
        # - If current price is significantly below the EMA, signal = +1 (buy).
        # - Otherwise, signal = 0 (no trade).
        signal = 0
        if (current_mid - kelp_avg_price) > deviation_threshold:
            signal = -1
        elif (kelp_avg_price - current_mid) > deviation_threshold:
            signal = 1

        ##################################################################
        # 4. FORMULATE DIRECTIONAL ORDER BASED ON THE MEAN REVERSION SIGNAL
        ##################################################################
        orders = []
        current_position = kelp_position

        # Set order size—use smaller sizes during the first ticks.
        if kelp_count < 20:
            max_order_size = 5
        else:
            max_order_size = 10

        if signal == 1:  # Buy signal: price is low relative to EMA.
            allowable_buy = 50 - current_position  # Maximum additional units that can be bought.
            if allowable_buy > 0:
                buy_quantity = min(max_order_size, allowable_buy)
                orders.append(Order(KELP, int(round(current_mid)), buy_quantity))
        elif signal == -1:  # Sell signal: price is high relative to EMA.
            allowable_sell = 50 + current_position  # Maximum additional units that can be sold.
            if allowable_sell > 0:
                sell_quantity = min(max_order_size, allowable_sell)
                orders.append(Order(KELP, int(round(current_mid)), -sell_quantity))

        result[KELP] = orders

        ##################################################################
        # 5. SERIALIZE UPDATED STATE
        ##################################################################
        updated_data = {
            "kelp_avg_price": kelp_avg_price,
            "kelp_count": kelp_count
        }
        traderData = json.dumps(updated_data)

        ##################################################################
        # 6. (OPTIONAL) CONVERSIONS OR OTHER ADJUSTMENTS
        ##################################################################
        conversions = 0

        return result, conversions, traderData