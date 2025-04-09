import json
import jsonpickle
import math
import statistics
from typing import Dict, List
from classes import *

# Type aliases
Time = int
Symbol = str
Product = str
Position = int
UserId = str
ObservationValue = int


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

        resin_position = state.position.get("RESIN", 0)

        result = {}

        ##################################################################
        # 1. UPDATE RUNNING PRICE AVERAGE
        ##################################################################

        if "RESIN" in state.order_depths:
            order_depth = state.order_depths["RESIN"]

            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                mid_price = (best_bid + best_ask) / 2.0
            else:
                mid_price = resin_avg_price

            alpha = 0.1  # smoothing factor
            new_avg_price = resin_avg_price * (1 - alpha) + mid_price * alpha
            resin_avg_price = new_avg_price
            resin_count += 1

        ##################################################################
        # 2. DETERMINE FAIR VALUE & ASYMMETRIC SPREAD
        ##################################################################
        if "RESIN" in state.order_depths:
            order_depth = state.order_depths["RESIN"]
            base_spread = 4.0

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

            max_order_size = 5
            allowable_buy = 50 - current_position
            allowable_sell = 50 + current_position

            buy_quantity = min(max_order_size, max(0, allowable_buy))
            sell_quantity = min(max_order_size, max(0, allowable_sell))

            if buy_quantity > 0:
                orders.append(Order("RESIN", buy_price, buy_quantity))
            if sell_quantity > 0:
                orders.append(Order("RESIN", sell_price, -sell_quantity))

            result["RESIN"] = orders

        ##################################################################
        # 4. SERIALIZE UPDATED STATE
        ##################################################################
        updated_data = {"resin_avg_price": resin_avg_price, "resin_count": resin_count}
        traderData = json.dumps(updated_data)

        ##################################################################
        # 5. (OPTIONAL) CONVERSIONS
        ##################################################################
        conversions = 0

        return result, conversions, traderData
