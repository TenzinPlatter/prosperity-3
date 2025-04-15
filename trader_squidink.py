import json
from typing import Dict, List

import json
import jsonpickle
import math
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

# Constants
SQUID = "SQUID_INK"


# Day-specific parameters based on price analysis
DAY_PARAMS = {
}


# Default parameters if day not recognized
DEFAULT_PARAMS = {
    "INIT_PRICE": 2000,
    "ALPHA_INIT": 0.2,
    "ALPHA_NORMAL": 0.05,
    "BASE_SPREAD": 3.0,
    "UP_WEIGHT": 0.4,
    "DOWN_WEIGHT": 0.2,
    "ORDER_SIZE_SMALL": 5,
    "ORDER_SIZE_LARGE": 15,
    "VOLATILITY_FACTOR": 0.3,
}


# Position limit
MAX_POS = 100


class Trader:
    def run(self, state: TradingState):


        ##################################################################
        # 0. UNPACK STATE AND INITIALIZE VARIABLES
        ##################################################################


        trader_memory = {}
        if state.traderData:
            try:
                trader_memory = json.loads(state.traderData)
            except:
                trader_memory = {}


        # Extract or initialize day parameter
        day = trader_memory.get("day", None)
       
        # First-time initialization: determine which day we're on
        if day is None:
            # Try to determine day from timestamp or initial pricing
            if SQUID in state.order_depths:
                od = state.order_depths[SQUID]
                if od.buy_orders and od.sell_orders:
                    mid_price = (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2
                    # Rough day estimation based on price ranges identified in data
                    if mid_price > 2000:
                        day = -2  # Higher price range
                    elif mid_price > 1950:
                        day = -1  # Medium price range
                    else:
                        day = 0   # Lower price range
                else:
                    day = 0  # Default to day 0 if can't determine
            else:
                day = 0  # Default to day 0 if can't determine
       
        # Get parameters for the current day
        params = DAY_PARAMS.get(day, DEFAULT_PARAMS)
       
        # Initialize or retrieve trading variables
        squid_avg = trader_memory.get("avg_price", params["INIT_PRICE"])
        tick_count = trader_memory.get("tick_count", 0)
        volatility = trader_memory.get("volatility", 10)
        momentum = trader_memory.get("momentum", 0)  # Track recent price momentum
        last_price = trader_memory.get("last_price", squid_avg)
        price_direction = trader_memory.get("price_direction", 0)


        result = {}


        if SQUID not in state.order_depths:
            # Return unchanged state if no market data
            trader_memory["day"] = day
            return {}, 0, json.dumps(trader_memory)


        order_depth = state.order_depths[SQUID]
        position = state.position.get(SQUID, 0)


        ##################################################################
        # 1. CALCULATE MID PRICE AND UPDATE AVERAGE PRICE
        ##################################################################


        if order_depth.buy_orders and order_depth.sell_orders:
            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            mid_price = (best_bid + best_ask) / 2
           
            # Calculate order book imbalance
            total_bid_volume = sum(order_depth.buy_orders.values())
            total_ask_volume = sum(abs(vol) for vol in order_depth.sell_orders.values())
            if total_bid_volume + total_ask_volume > 0:
                imbalance = (total_bid_volume - total_ask_volume) / (total_bid_volume + total_ask_volume)
            else:
                imbalance = 0
           
            # Update price direction and momentum
            if mid_price > last_price:
                current_direction = 1
            elif mid_price < last_price:
                current_direction = -1
            else:
                current_direction = 0
               
            # Strong trend continuation or reversal detection
            if current_direction == price_direction:
                # Continuing trend
                momentum = min(momentum + 0.2, 1.0)
            elif current_direction != 0 and price_direction != 0:
                # Trend reversal
                momentum = max(momentum - 0.4, -1.0)
           
            price_direction = current_direction if current_direction != 0 else price_direction
            last_price = mid_price
        else:
            mid_price = squid_avg
            imbalance = 0


        # Select alpha based on initialization phase and day parameters
        if tick_count < 50:
            alpha = params["ALPHA_INIT"]
        else:
            # Adjust alpha based on detected momentum
            if abs(momentum) > 0.6:
                # Higher alpha during strong trends
                alpha = params["ALPHA_NORMAL"] * 1.3
            else:
                alpha = params["ALPHA_NORMAL"]


        # Update average price estimate
        squid_avg = (1 - alpha) * squid_avg + alpha * mid_price
        tick_count += 1


        ##################################################################
        # 2. CALCULATE FAIR VALUE AND DYNAMIC SPREAD
        ##################################################################


        price_diff = mid_price - squid_avg
        price_deviation = abs(price_diff)
       
        # Update volatility estimate - more responsive during high volatility periods
        volatility_update_rate = 0.1 if abs(price_deviation) < volatility else 0.15
        volatility = (1 - volatility_update_rate) * volatility + volatility_update_rate * price_deviation


        # Calculate dynamic spread based on volatility and day parameters
        base_spread = params["BASE_SPREAD"]
        volatility_factor = params["VOLATILITY_FACTOR"]
        spread_adjust = min(max(volatility * volatility_factor, 0), 8)
       
        # Position-based spread adjustment
        position_factor = min(abs(position) / 60, 1.0)  # Scale based on position size
        if position > 30:  # Significant long position
            position_adjust = position_factor * 1.5  # Wider spread when long
        elif position < -30:  # Significant short position
            position_adjust = position_factor * 1.5  # Wider spread when short
        else:
            position_adjust = 0
           
        # Final spread calculation
        spread = base_spread + spread_adjust + position_adjust
       
        # Set fair value with some bias based on order imbalance
        fair_value = squid_avg + (imbalance * volatility * 0.15)


        buy_price = fair_value - spread / 2
        sell_price = fair_value + spread / 2


        # Asymmetry based on price trend and day parameters
        if price_diff > 0:
            # Current price above average - lean into uptrend, but prepare for reversal
            sell_price += price_diff * params["UP_WEIGHT"]
            buy_price -= price_diff * params["DOWN_WEIGHT"]
        else:
            # Current price below average - lean into downtrend, but prepare for reversal
            buy_price += price_diff * params["UP_WEIGHT"]
            sell_price -= price_diff * params["DOWN_WEIGHT"]
           
        # Additional asymmetry based on detected momentum
        momentum_factor = 0.15 * momentum
        buy_price += momentum_factor
        sell_price += momentum_factor


        # Ensure integer prices
        buy_price = int(round(buy_price))
        sell_price = int(round(sell_price))


        ##################################################################
        # 3. DETERMINE ORDER SIZE AND POSITION CONSTRAINTS
        ##################################################################


        # Dynamic order sizing based on market phase and volatility
        if tick_count < 40:
            max_order_size = params["ORDER_SIZE_SMALL"]
        else:
            # Adjust order size based on volatility and position
            volatility_size_factor = min(max(1.0 - (volatility / 30), 0.7), 1.2)
            position_size_factor = 1.0 - (abs(position) / (MAX_POS * 1.5))
            size_factor = min(volatility_size_factor * position_size_factor, 1.0)
            max_order_size = max(1, int(params["ORDER_SIZE_LARGE"] * size_factor))


        # Position limits
        max_buy = MAX_POS - position
        max_sell = MAX_POS + position


        # Final order volumes
        buy_volume = min(max_order_size, max(0, max_buy))
        sell_volume = min(max_order_size, max(0, max_sell))


        ##################################################################
        # 4. GENERATE ORDERS
        ##################################################################


        orders = []
        if buy_volume > 0:
            orders.append(Order(SQUID, buy_price, buy_volume))
        if sell_volume > 0:
            orders.append(Order(SQUID, sell_price, -sell_volume))


        result[SQUID] = orders


        ##################################################################
        # 5. SERIALIZE TRADER STATE
        ##################################################################


        updated_memory = {
            "avg_price": squid_avg,
            "tick_count": tick_count,
            "volatility": volatility,
            "day": day,
            "momentum": momentum,
            "last_price": last_price,
            "price_direction": price_direction
        }


        traderData = json.dumps(updated_memory)
        conversions = 0


        return result, conversions, traderData


