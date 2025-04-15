import json
import math
from typing import Dict, List
import numpy as np

# Type aliases
Time = int
Symbol = str
Product = str
Position = int
UserId = str
ObservationValue = int

# Constants (example; adjust as needed)
KELP = "KELP"  # Unused here, but kept from your code.
# The products for our pair trading:
BASKET = "PICNIC_BASKET1"
CROISSANTS = "CROISSANTS"
JAMS = "JAMS"
DJEMBES = "DJEMBES"

############################################
# Data model classes (unchanged)
############################################

class Listing:
    def __init__(self, symbol: Symbol, product: Product, denomination: Product):
        self.symbol = symbol
        self.product = product
        self.denomination = denomination

class ConversionObservation:
    def __init__(self, bidPrice: float, askPrice: float, transportFees: float,
                 exportTariff: float, importTariff: float, sugarPrice: float,
                 sunlightIndex: float):
        self.bidPrice = bidPrice
        self.askPrice = askPrice
        self.transportFees = transportFees
        self.exportTariff = exportTariff
        self.importTariff = importTariff
        self.sugarPrice = sugarPrice
        self.sunlightIndex = sunlightIndex

class Observation:
    def __init__(self,
                 plainValueObservations: Dict[Product, ObservationValue],
                 conversionObservations: Dict[Product, ConversionObservation]) -> None:
        self.plainValueObservations = plainValueObservations
        self.conversionObservations = conversionObservations

    def __str__(self) -> str:
        return "(plainValueObservations: " + json.dumps(self.plainValueObservations) + \
               ", conversionObservations: " + json.dumps(self.conversionObservations) + ")"

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
    def __init__(self, symbol: Symbol, price: int, quantity: int,
                 buyer: UserId | None = None, seller: UserId | None = None,
                 timestamp: int = 0) -> None:
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
        self.buyer = buyer
        self.seller = seller
        self.timestamp = timestamp

    def __str__(self) -> str:
        return f"({self.symbol}, {self.buyer} << {self.seller}, {self.price}, {self.quantity}, {self.timestamp})"

    def __repr__(self) -> str:
        return self.__str__()

class TradingState:
    def __init__(self,
                 traderData: str,
                 timestamp: Time,
                 listings: Dict[Symbol, Listing],
                 order_depths: Dict[Symbol, OrderDepth],
                 own_trades: Dict[Symbol, List[Trade]],
                 market_trades: Dict[Symbol, List[Trade]],
                 position: Dict[Product, Position],
                 observations: Observation):
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

############################################
# Trader class: Pair Trading using Premium Formula with Rolling Volatility
############################################

class Trader:
    def run(self, state: TradingState):
        """
        Implements a pair trading strategy for PICNIC_BASKET1.
        Uses EMAs for price estimation and a rolling standard deviation over 1000 observations
        to calculate volatility, consistent with the regression code.
        """
        # -------------------------------
        # 1. UNPACK/INITIALIZE PERSISTED STATE
        try:
            previous_data = json.loads(state.traderData)
        except Exception:
            previous_data = {}
        
        # Retrieve persisted state for price EMAs.
        croissants_ema = previous_data.get("croissants_ema", None)
        jams_ema = previous_data.get("jams_ema", None)
        djembes_ema = previous_data.get("djembes_ema", None)
        
        # Retrieve historical mid–prices (for volatility calculation).
        croissants_history = previous_data.get("croissants_history", [])
        jams_history = previous_data.get("jams_history", [])
        djembes_history = previous_data.get("djembes_history", [])
        
        # (Optional) Persist djembes volume average, if needed.
        djembes_volume_avg = previous_data.get("djembes_volume_avg", 0.0)
        
        smoothing_alpha = 0.1  # Smoothing parameter for the EMA updates.
        window = 1000  # Same window as used in regression for rolling volatility.

        # -------------------------------
        # 2. RETRIEVE CURRENT MID PRICES FROM ORDER DEPTHS
        symbols = [BASKET, CROISSANTS, JAMS, DJEMBES]
        mid_prices = {}
        for sym in symbols:
            if sym in state.order_depths:
                depth = state.order_depths[sym]
                if depth.buy_orders and depth.sell_orders:
                    best_bid = max(depth.buy_orders.keys())
                    best_ask = min(depth.sell_orders.keys())
                    mid_prices[sym] = (best_bid + best_ask) / 2.0
                else:
                    mid_prices[sym] = None
            else:
                mid_prices[sym] = None
        
        if any(mid_prices[sym] is None for sym in symbols):
            return {}, 0, state.traderData
        
        # -------------------------------
        # 3. UPDATE PRICE EMAs FOR CROISSANTS, JAMS, DJEMBES
        # Initialize with the current price if no previous EMA exists.
        croissants_ema = (
            mid_prices[CROISSANTS]
            if croissants_ema is None
            else smoothing_alpha * mid_prices[CROISSANTS] + (1 - smoothing_alpha) * croissants_ema
        )
        jams_ema = (
            mid_prices[JAMS]
            if jams_ema is None
            else smoothing_alpha * mid_prices[JAMS] + (1 - smoothing_alpha) * jams_ema
        )
        djembes_ema = (
            mid_prices[DJEMBES]
            if djembes_ema is None
            else smoothing_alpha * mid_prices[DJEMBES] + (1 - smoothing_alpha) * djembes_ema
        )
        
        # -------------------------------
        # 3b. UPDATE Volatility Histories and Compute Rolling Volatility
        # Append current mid–price to history for each product.
        croissants_history.append(mid_prices[CROISSANTS])
        jams_history.append(mid_prices[JAMS])
        djembes_history.append(mid_prices[DJEMBES])
        
        # Keep only the latest "window" observations.
        if len(croissants_history) > window:
            croissants_history = croissants_history[-window:]
        if len(jams_history) > window:
            jams_history = jams_history[-window:]
        if len(djembes_history) > window:
            djembes_history = djembes_history[-window:]
        
        # Compute the rolling volatility as the standard deviation over the window.
        croissants_vol = float(np.std(croissants_history)) if len(croissants_history) > 1 else 0.0
        jams_vol = float(np.std(jams_history)) if len(jams_history) > 1 else 0.0
        djembes_vol = float(np.std(djembes_history)) if len(djembes_history) > 1 else 0.0
        
        # Update djembes volume average (unchanged from previous method).
        if djembes_volume_avg == 0:
            djembes_volume_avg = mid_prices[DJEMBES]
        else:
            djembes_volume_avg = (1 - smoothing_alpha) * djembes_volume_avg + smoothing_alpha * mid_prices[DJEMBES]
        
        # -------------------------------
        # 4. CALCULATE PREMIUM USING THE REGRESSION-BASED FORMULA
        # Use EMAs for price and rolling volatilities for volatility measures.
        # Note: The premium formula below uses the standard deviation computed above.
        alpha_const = -56
        predicted_premium = (alpha_const +
                              20.5387 * croissants_vol +
                              3.057 * jams_vol +
                              0.7469 * djembes_vol)
        
        # -------------------------------
        # 5. COMPUTE FAIR VALUE, COMPUTED VALUE, AND PREMIUM DIFFERENCES
        # Fair Value is calculated from the EMAs.
        fair_value = 6 * croissants_ema + 3 * jams_ema + 1 * djembes_ema
        computed_value = fair_value + predicted_premium
        basket_price = mid_prices[BASKET]
        
        print(f"Mid–Prices: {mid_prices}")
        print(f"EMAs: CROISSANTS={croissants_ema:.2f}, JAMS={jams_ema:.2f}, DJEMBES={djembes_ema:.2f}")
        print(f"Volatilities: Croissants={croissants_vol:.4f}, Jams={jams_vol:.4f}, Djembes={djembes_vol:.4f}")
        print(f"Djembes Volume (avg) = {djembes_volume_avg:.2f}")
        print(f"Predicted Premium = {predicted_premium:.2f}")
        print(f"Fair Value (from EMAs) = {fair_value:.2f}, Computed Value = {computed_value:.2f}")
        print(f"Basket Price = {basket_price:.2f}")
        
        # Calculate observed premium (the difference between basket price and fair value)
        observed_premium = basket_price - fair_value
        premium_difference = observed_premium - predicted_premium
        print(f"Observed Premium (Basket Price - Fair Value) = {observed_premium:.2f}")
        print(f"Difference between Observed and Predicted Premium = {premium_difference:.2f}")
        
        # -------------------------------
        # 6. GENERATE TRADING SIGNAL BASED ON DEVIATION
        threshold = 10.0  # Define a threshold for taking action.
        if basket_price > computed_value + threshold:
            signal = -1  # Basket overpriced: signal to short basket and buy constituents.
        elif basket_price < computed_value - threshold:
            signal = 1   # Basket underpriced: signal to buy basket and short constituents.
        else:
            signal = 0
        
        print(f"Trade Signal: {signal} (Threshold: ±{threshold})")
        
        # -------------------------------
        # 7. FORMULATE ORDERS
        orders: Dict[str, List[Order]] = {}
        pos_basket = state.position.get(BASKET, 0)
        pos_croissants = state.position.get(CROISSANTS, 0)
        pos_jams = state.position.get(JAMS, 0)
        pos_djembes = state.position.get(DJEMBES, 0)
        
        max_order = 10  # Maximum units to trade per signal.
        orders_list = []
        if signal == -1:
            # Basket overpriced -> short basket, long constituents.
            orders_list.append(Order(BASKET, int(round(basket_price)), -max_order))
            #orders_list.append(Order(CROISSANTS, int(round(mid_prices[CROISSANTS])), 6 * max_order))
            orders_list.append(Order(JAMS, int(round(mid_prices[JAMS])), -3 * max_order))
            orders_list.append(Order(DJEMBES, int(round(mid_prices[DJEMBES])), -1 * max_order))
        elif signal == 1:
            # Basket underpriced -> long basket, short constituents.
            orders_list.append(Order(BASKET, int(round(basket_price)), max_order))
            #orders_list.append(Order(CROISSANTS, int(round(mid_prices[CROISSANTS])), -6 * max_order))
            orders_list.append(Order(JAMS, int(round(mid_prices[JAMS])), 3 * max_order))
            orders_list.append(Order(DJEMBES, int(round(mid_prices[DJEMBES])), 1 * max_order))
        else:
            orders_list = []
        
        for order in orders_list:
            orders.setdefault(order.symbol, []).append(order)
        
        # -------------------------------
        # 8. UPDATE AND SERIALIZE STATE
        new_state = {
            "croissants_ema": croissants_ema,
            "jams_ema": jams_ema,
            "djembes_ema": djembes_ema,
            "croissants_history": croissants_history,
            "jams_history": jams_history,
            "djembes_history": djembes_history,
            "djembes_volume_avg": djembes_volume_avg
        }
        traderData = json.dumps(new_state)
        
        return orders, 0, traderData
