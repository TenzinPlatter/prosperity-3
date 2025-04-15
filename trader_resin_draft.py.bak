import json
import jsonpickle
import math #hello
import statistics
from typing import Dict, List

# Type aliases
Time = int
Symbol = str
Product = str
Position = int
UserId = str
ObservationValue = int

# Constants
RESIN = "RAINFOREST_RESIN"
# start
ALPHA_EARLY = 0.0
ALPHA_LATE = 0.0
BASESPREAD = 0.0
ADJUST_SCALE = 0.0
MAX_ORDER_EARLY = 0.0
MAX_ORDER_LATE = 2.1
# end

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
        sunlightIndex: float,
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
        conversionObservations: Dict[Product, ConversionObservation],
    ) -> None:
        self.plainValueObservations = plainValueObservations
        self.conversionObservations = conversionObservations

    def __str__(self) -> str:
        return (
            "(plainValueObservations: "
            + jsonpickle.encode(self.plainValueObservations)
            + ", conversionObservations: "
            + jsonpickle.encode(self.conversionObservations)
            + ")"
        )


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
        timestamp: int = 0,
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
        observations: Observation,
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
        # 0. UNPACK / INITIALIZE
        ##################################################################

        previous_data = {}
        if state.traderData:
            try:
                previous_data = json.loads(state.traderData)
            except:
                previous_data = {}

        # On the very first run, resin_avg_price might remain at 100 if there's no market data.
        resin_avg_price = previous_data.get("resin_avg_price", 100.0)
        resin_count = previous_data.get("resin_count", 0)
        resin_position = state.position.get(RESIN, 0)

        result = {}

        ##################################################################
        # 1. INITIAL SEEDING OF RUNNING PRICE AVERAGE (FIRST TICK ONLY)
        ##################################################################
        if RESIN in state.order_depths and resin_count == 0:
            order_depth = state.order_depths[RESIN]
            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                # Use this first mid-price to seed the average
                resin_avg_price = (best_bid + best_ask) / 2.0

        ##################################################################
        # 2. UPDATE RUNNING PRICE AVERAGE
        ##################################################################
        if RESIN in state.order_depths:
            order_depth = state.order_depths[RESIN]
            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                mid_price = (best_bid + best_ask) / 2.0
            else:
                mid_price = resin_avg_price

            # Use a higher alpha in early ticks to adapt faster, then revert to default
            if resin_count < 20:
                alpha = 0.2
            else:
                alpha = 0.055

            # Exponential smoothing
            resin_avg_price = resin_avg_price * (1 - alpha) + mid_price * alpha
            resin_count += 1

        ##################################################################
        # 3. DETERMINE FAIR VALUE & ASYMMETRIC SPREAD
        ##################################################################
        if RESIN in state.order_depths:
            order_depth = state.order_depths[RESIN]
            base_spread = 0.7

            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                current_mid = (best_bid + best_ask) / 2.0
            else:
                current_mid = resin_avg_price

            diff = current_mid - resin_avg_price
            adjust_scale = 0.5
            fair_value = resin_avg_price

            buy_price = fair_value - base_spread / 2
            sell_price = fair_value + base_spread / 2

            # Asymmetric shift
            if diff > 0:
                sell_price += diff * adjust_scale
                buy_price -= diff * (adjust_scale / 2)
            else:
                buy_price += diff * adjust_scale
                sell_price -= diff * (adjust_scale / 2)

            # Round to nearest integer for your market's tick size
            buy_price = int(round(buy_price))
            sell_price = int(round(sell_price))

            ##################################################################
            # 4. CHECK POSITION LIMITS & FORMULATE ORDERS
            ##################################################################
            orders = []
            current_position = resin_position

            # Smaller order size during warm-up
            if resin_count < 20:
                max_order_size = 5
            else:
                max_order_size = 10

            allowable_buy = 50 - current_position  # how many we can still buy
            allowable_sell = (
                50 + current_position
            )  # how many we can still sell (position can go -50)

            buy_quantity = min(max_order_size, max(0, allowable_buy))
            sell_quantity = min(max_order_size, max(0, allowable_sell))

            if buy_quantity > 0:
                orders.append(Order(RESIN, buy_price, buy_quantity))
            if sell_quantity > 0:
                orders.append(Order(RESIN, sell_price, -sell_quantity))

            result[RESIN] = orders

        ##################################################################
        # 5. SERIALIZE UPDATED STATE
        ##################################################################
        updated_data = {"resin_avg_price": resin_avg_price, "resin_count": resin_count}
        traderData = json.dumps(updated_data)

        ##################################################################
        # 6. (OPTIONAL) CONVERSIONS
        ##################################################################
        conversions = 0

        return result, conversions, traderData
