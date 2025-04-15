import pandas as pd
import numpy as np
import statistics
import math
from typing import Dict, List
import jsonpickle
#Grid search Parameters: mispricing threshold, vol estimate, hedge batch, rolling spread alpha, initial rolling spread fraction
# ---------------------------
# Global Constants
# ---------------------------
DEFAULT_EST_VOL = 0.2               # Default estimated volatility if none is stored.
TTE = 5.0 / 365.0                   # Time-to-expiry (5 days expressed as fraction of a year).
R = 0.0                             # Risk-free rate (assumed zero in this simulation).
UNDERLYING_LIMIT = 400              # Position limit for the underlying VOLCANIC_ROCK.
OPTION_LIMIT = 200                  # Position limit for any individual option voucher.
MAX_OPTION_TRADE_SIZE = 10          # Maximum number of options to trade per iteration.
MISPRICE_THRESHOLD = 0.4            # Minimum absolute mispricing difference to trigger trading.
HEDGE_BATCH = 5                     # Maximum number of underlying units to trade per hedging order.
DEFAULT_ROLLING_SPREAD_FRACTION = 0.02  # Default fallback spread as 2% of underlying_mid.
ALPHA_SPREAD = 0.1                  # Smoothing factor for updating the rolling spread.

# ---------------------------
# Type Aliases
# ---------------------------
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
    """Approximation of the standard normal CDF using error function."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def pdf(x: float) -> float:
    """Standard normal PDF."""
    return 1.0 / math.sqrt(2 * math.pi) * math.exp(-0.5 * x * x)

def black_scholes_call_price(
    S: float,  # current underlying price
    K: float,  # strike
    T: float,  # time to expiry (years)
    r: float,  # interest rate
    sigma: float  # volatility
) -> float:
    """Basic Black–Scholes formula for a European call."""
    if T <= 0 or sigma <= 0:
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
    """Delta of a European call under Black–Scholes (N(d1))."""
    if T <= 0 or sigma <= 0:
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
                T = TTE (5/365)
                r = R
                sigma = stored in traderData or DEFAULT_EST_VOL
          - Compare the market mid to the theoretical price:
                if market >> theo => short
                if market << theo => buy
          - Hedge total delta with trades on 'VOLCANIC_ROCK'.
          - Ensure position limits: ±OPTION_LIMIT for each option, ±UNDERLYING_LIMIT underlying.
        """

        # -------- 0. Restore or init persistent data --------
        previous_data = {}
        if state.traderData:
            try:
                previous_data = jsonpickle.decode(state.traderData)
            except Exception:
                previous_data = {}

        # Retrieve stored volatility or default
        est_vol = previous_data.get("est_vol", DEFAULT_EST_VOL)

        # -------- 1. Get Underlying Mid Price --------
        underlying_symbol = VOLCANIC_ROCK
        underlying_mid = previous_data.get("last_underlying_price", 100.0)
        if underlying_symbol in state.order_depths:
            depth_und = state.order_depths[underlying_symbol]
            if depth_und.buy_orders and depth_und.sell_orders:
                best_bid_live = max(depth_und.buy_orders.keys())
                best_ask_live = min(depth_und.sell_orders.keys())
                underlying_mid = (best_bid_live + best_ask_live) / 2.0

        previous_data["last_underlying_price"] = underlying_mid

        # -------- 2. Build Orders for Options --------
        result = {}
        conversions = 0  # not used here
        net_option_delta = 0.0

        # Evaluate each voucher option symbol for VOLCANIC_ROCK
        for symbol, depth in state.order_depths.items():
            if symbol == underlying_symbol:
                continue
            if not symbol.startswith("VOLCANIC_ROCK_VOUCHER_"):
                continue

            try:
                strike_part = symbol.split("_")[-1]
                K = float(strike_part)
            except Exception:
                continue

            # Compute market mid price for the option
            if depth.buy_orders and depth.sell_orders:
                best_bid = max(depth.buy_orders.keys())
                best_ask = min(depth.sell_orders.keys())
                option_mid = (best_bid + best_ask) / 2.0
            else:
                continue

            # Compute theoretical price and delta
            theo_price = black_scholes_call_price(underlying_mid, K, TTE, R, est_vol)
            call_delta = black_scholes_call_delta(underlying_mid, K, TTE, R, est_vol)
            diff = option_mid - theo_price

            current_pos = state.position.get(symbol, 0)
            orders_for_symbol = []

            # Overpriced: short the option if difference is greater than threshold
            if diff > MISPRICE_THRESHOLD:
                max_shortable = OPTION_LIMIT + current_pos
                if max_shortable > 0:
                    quantity = min(int(max_shortable), MAX_OPTION_TRADE_SIZE)
                    if quantity > 0:
                        orders_for_symbol.append(Order(symbol, int(math.floor(best_bid)), -quantity))
            # Underpriced: buy the option if difference is lower than -threshold
            elif diff < -MISPRICE_THRESHOLD:
                max_buyable = OPTION_LIMIT - current_pos
                if max_buyable > 0:
                    quantity = min(int(max_buyable), MAX_OPTION_TRADE_SIZE)
                    if quantity > 0:
                        orders_for_symbol.append(Order(symbol, int(math.ceil(best_ask)), quantity))

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
        rolling_spread = previous_data.get("rolling_spread", underlying_mid * DEFAULT_ROLLING_SPREAD_FRACTION)
        depth_und = state.order_depths.get(underlying_symbol, None)
        if depth_und and depth_und.buy_orders and depth_und.sell_orders:
            live_bid = max(depth_und.buy_orders.keys())
            live_ask = min(depth_und.sell_orders.keys())
            best_bid = live_bid
            best_ask = live_ask
            current_spread = live_ask - live_bid
            rolling_spread = rolling_spread * (1 - ALPHA_SPREAD) + current_spread * ALPHA_SPREAD
        else:
            best_bid = underlying_mid - rolling_spread / 2.0
            best_ask = underlying_mid + rolling_spread / 2.0

        previous_data["rolling_spread"] = rolling_spread

        # Place hedging orders in the underlying
        hedge_orders = []
        if delta_diff > 0:
            allowed_buy = UNDERLYING_LIMIT - current_underlying_pos
            buy_quantity = min(int(abs(delta_diff)), HEDGE_BATCH, int(allowed_buy))
            if buy_quantity > 0:
                hedge_orders.append(Order(underlying_symbol, int(math.ceil(best_ask)), buy_quantity))
        elif delta_diff < 0:
            allowed_sell = UNDERLYING_LIMIT + current_underlying_pos
            sell_quantity = min(int(abs(delta_diff)), HEDGE_BATCH, int(allowed_sell))
            if sell_quantity > 0:
                hedge_orders.append(Order(underlying_symbol, int(math.floor(best_bid)), -sell_quantity))
        if hedge_orders:
            result[underlying_symbol] = hedge_orders

        # -------- 4. Serialize Updated Trader Data --------
        new_trader_data = previous_data
        traderData = jsonpickle.encode(new_trader_data)

        return result, conversions, traderData
