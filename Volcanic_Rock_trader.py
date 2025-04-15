import pandas as pd
import numpy as np
import statistics
import math
from typing import Dict, List
import jsonpickle

# Type aliases
Time = int
Symbol = str
Product = str
Position = int

VOLCANIC_ROCK = "VOLCANIC_ROCK"

################################################
# Data model classes (similar to your example)
################################################

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
        plainValueObservations: Dict[Product, int],
        conversionObservations: Dict[Product, ConversionObservation]
    ) -> None:
        self.plainValueObservations = plainValueObservations
        self.conversionObservations = conversionObservations

    def __str__(self) -> str:
        return "(plainValueObservations: " + jsonpickle.encode(self.plainValueObservations) + \
               ", conversionObservations: " + jsonpickle.encode(self.conversionObservations) + ")"

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
        buyer: str | None = None,
        seller: str | None = None,
        timestamp: int = 0
    ) -> None:
        self.symbol = symbol
        self.price: int = price
        self.quantity = quantity
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
        return jsonpickle.encode(self, indent=4)

################################################
# Black–Scholes utility functions
################################################

def cdf(x: float) -> float:
    """
    Approximation of the standard normal CDF using error function.
    """
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def pdf(x: float) -> float:
    """
    Standard normal PDF.
    """
    return 1.0 / math.sqrt(2 * math.pi) * math.exp(-0.5 * x * x)

def black_scholes_call_price(
    S: float,  # current underlying price
    K: float,  # strike
    T: float,  # time to expiry (years)
    r: float,  # interest rate
    sigma: float  # volatility
) -> float:
    """
    Basic Black–Scholes formula for a European call.
    """
    if T <= 0:
        return max(S - K, 0)
    if sigma <= 0:
        return max(S - K, 0)

    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    return S * cdf(d1) - K * math.exp(-r * T) * cdf(d2)

def black_scholes_call_delta(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float
) -> float:
    """
    Delta of a European call under Black–Scholes (N(d1)).
    """
    if T <= 0 or sigma <= 0:
        # If no time or no vol, delta is either 0 or 1 if in-the-money
        return 1.0 if S > K else 0.0

    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return cdf(d1)

################################################
# Trader Class
################################################

class Trader:
    def run(self, state: TradingState):
        """
        Strategy:
          - We consider the underlying commodity 'VOLCANIC_ROCK'.
          - We consider calls (vouchers) named 'VOLCANIC_ROCK_VOUCHER_{strike}'.
          - For each voucher, compute a theoretical BS price & delta using:
              S = mid price of VOLCANIC_ROCK
              T = 5/365
              r = 0
              sigma = stored in traderData or 0.2 default
          - Compare the market mid to the theoretical price:
              if market >> theo => short
              if market << theo => buy
          - Hedge total delta with trades on 'VOLCANIC_ROCK'.
          - Ensure position limits: ±200 each option, ±400 underlying.
        """

        # -------- 0. Restore or init persistent data --------
        previous_data = {}
        if state.traderData:
            try:
                previous_data = jsonpickle.decode(state.traderData)
            except:
                previous_data = {}

        # A simple volatility estimate we keep in traderData
        est_vol = previous_data.get("est_vol", 0.2)

        # TTE = 5/365 ~ 0.0137
        TTE = 5.0 / 365.0
        r = 0.0

        # Underlying info
        underlying_symbol = VOLCANIC_ROCK
        underlying_limit = 400

        # Option position limit
        option_limit = 200

        # -------- 1. Get Underlying Mid Price --------
        underlying_mid = previous_data.get("last_underlying_price", 100.0)
        if underlying_symbol in state.order_depths:
            depth_und = state.order_depths[underlying_symbol]
            if depth_und.buy_orders and depth_und.sell_orders:
                best_bid_live = max(depth_und.buy_orders.keys())
                best_ask_live = min(depth_und.sell_orders.keys())
                underlying_mid = (best_bid_live + best_ask_live) / 2.0

        # Store for next time
        previous_data["last_underlying_price"] = underlying_mid

        # -------- 2. Build Orders for Options --------
        result = {}
        conversions = 0  # not used here
        net_option_delta = 0.0

        # Threshold for deciding mispricing
        misprice_threshold = 0.4

        # Evaluate each voucher option symbol for VOLCANIC_ROCK
        for symbol, depth in state.order_depths.items():
            # Skip underlying
            if symbol == underlying_symbol:
                continue

            # Check if symbol is a voucher option
            if not symbol.startswith("VOLCANIC_ROCK_VOUCHER_"):
                continue

            # Parse strike value from symbol: "VOLCANIC_ROCK_VOUCHER_9500"
            try:
                strike_part = symbol.split("_")[-1]
                K = float(strike_part)
            except:
                continue

            # Compute market mid price for the option
            if depth.buy_orders and depth.sell_orders:
                best_bid = max(depth.buy_orders.keys())
                best_ask = min(depth.sell_orders.keys())
                option_mid = (best_bid + best_ask) / 2.0
            else:
                continue  # Skip if no live quotes

            # Compute theoretical price and call delta using Black–Scholes
            theo_price = black_scholes_call_price(underlying_mid, K, TTE, r, est_vol)
            call_delta = black_scholes_call_delta(underlying_mid, K, TTE, r, est_vol)

            diff = option_mid - theo_price
            current_pos = state.position.get(symbol, 0)
            orders_for_symbol = []

            # Overpriced: short the option
            if diff > misprice_threshold:
                max_shortable = option_limit + current_pos  # current_pos is negative if already short
                if max_shortable > 0:
                    quantity = min(int(max_shortable), 10)  # trade up to 10 units
                    if quantity > 0:
                        orders_for_symbol.append(Order(symbol, int(math.floor(best_bid)), -quantity))
            # Underpriced: buy the option
            elif diff < -misprice_threshold:
                max_buyable = option_limit - current_pos
                if max_buyable > 0:
                    quantity = min(int(max_buyable), 10)
                    if quantity > 0:
                        orders_for_symbol.append(Order(symbol, int(math.ceil(best_ask)), quantity))

            # Accumulate net delta from current position and proposed trades
            net_option_delta += current_pos * call_delta
            fill_qty = sum(o.quantity for o in orders_for_symbol)
            net_option_delta += fill_qty * call_delta

            if orders_for_symbol:
                result[symbol] = orders_for_symbol

        # -------- 3. Delta Hedge with the Underlying --------
        current_underlying_pos = state.position.get(underlying_symbol, 0)
        desired_underlying_pos = -net_option_delta
        delta_diff = desired_underlying_pos - current_underlying_pos

        # --- Rolling Spread logic for underlying fallback ---
        # Retrieve the rolling spread from persistent data, defaulting to 2% of underlying_mid
        rolling_spread = previous_data.get("rolling_spread", underlying_mid * 0.02)
        depth_und = state.order_depths.get(underlying_symbol, None)
        if depth_und and depth_und.buy_orders and depth_und.sell_orders:
            live_bid = max(depth_und.buy_orders.keys())
            live_ask = min(depth_und.sell_orders.keys())
            best_bid = live_bid
            best_ask = live_ask
            # Update the rolling spread with the observed live spread
            current_spread = live_ask - live_bid
            alpha_spread = 0.1  # smoothing factor
            rolling_spread = rolling_spread * (1 - alpha_spread) + current_spread * alpha_spread
        else:
            # Fallback: use the rolling spread to compute best_bid and best_ask
            best_bid = underlying_mid - rolling_spread / 2.0
            best_ask = underlying_mid + rolling_spread / 2.0
        previous_data["rolling_spread"] = rolling_spread

        # Proceed with the hedging orders, up to a batch of 5
        hedge_batch = 5
        underlying_orders = []
        if delta_diff > 0:
            allowed_buy = underlying_limit - current_underlying_pos
            buy_quantity = min(int(abs(delta_diff)), hedge_batch, int(allowed_buy))
            if buy_quantity > 0:
                underlying_orders.append(Order(underlying_symbol, int(math.ceil(best_ask)), buy_quantity))
        elif delta_diff < 0:
            allowed_sell = underlying_limit + current_underlying_pos
            sell_quantity = min(int(abs(delta_diff)), hedge_batch, int(allowed_sell))
            if sell_quantity > 0:
                underlying_orders.append(Order(underlying_symbol, int(math.floor(best_bid)), -sell_quantity))
        if underlying_orders:
            result[underlying_symbol] = underlying_orders

        # -------- 4. Serialize Updated Trader Data --------
        new_trader_data = previous_data
        traderData = jsonpickle.encode(new_trader_data)

        return result, conversions, traderData
