import os
import time
import json
import hmac
import hashlib
import urllib.request
import urllib.parse
from decimal import Decimal, ROUND_HALF_UP
import config

PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "portfolio_state.json")

def round_to_tick(price, tick_size_str):
    d_price = Decimal(str(price))
    d_tick = Decimal(str(tick_size_str))
    rounded = (d_price / d_tick).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * d_tick
    return format(rounded, 'f')

class DeltaClient:
    def __init__(self):
        self.api_key = config.DELTA_API_KEY
        self.api_secret = config.DELTA_API_SECRET
        self.base_url = config.DELTA_BASE_URL
        self.paper_mode = config.PAPER_TRADING
        self.portfolio = self._load_portfolio()
        self.cached_products = {}
        self.refresh_products()

    def _load_portfolio(self):
        default = {
            "virtual_balance": config.VIRTUAL_INITIAL_BALANCE,
            "realized_pnl": 0.0,
            "open_positions": {},
            "trade_history": [],
            "cooldowns": {}
        }
        if os.path.exists(PORTFOLIO_FILE):
            try:
                with open(PORTFOLIO_FILE, "r") as f:
                    data = json.load(f)
                    default.update(data)
            except Exception as e:
                print(f"[DELTA] Portfolio read note: {e}")
        return default

    def save_portfolio(self):
        try:
            with open(PORTFOLIO_FILE, "w") as f:
                json.dump(self.portfolio, f, indent=2)
        except Exception as e:
            print(f"[DELTA] Portfolio save note: {e}")

    def _api_request(self, method, path, query_params=None, payload_dict=None):
        if not self.api_key or not self.api_secret:
            return {"error": "Missing API Key/Secret"}

        url = f"{self.base_url}{path}"
        if query_params:
            url += f"?{urllib.parse.urlencode(query_params)}"

        payload_str = json.dumps(payload_dict, separators=(",", ":")) if payload_dict else ""
        timestamp = str(int(time.time()))
        signature_data = method + timestamp + path + (f"?{urllib.parse.urlencode(query_params)}" if query_params else "") + payload_str
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            signature_data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        headers = {
            "api-key": self.api_key,
            "timestamp": timestamp,
            "signature": signature,
            "User-Agent": "WhaleGoldenPocketBot/1.0",
            "Content-Type": "application/json"
        }

        data = payload_str.encode('utf-8') if payload_str else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            return {"error": f"HTTP {e.code}", "body": body}
        except Exception as e:
            return {"error": str(e)}

    def refresh_products(self):
        try:
            url = f"{self.base_url}/v2/products"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as r:
                res = json.loads(r.read().decode('utf-8')).get('result', [])
                for p in res:
                    sym = p.get('symbol')
                    if sym:
                        self.cached_products[sym] = p
        except Exception as e:
            print(f"[DELTA] Products refresh error: {e}")

    def get_ticker(self, symbol):
        try:
            url = f"{self.base_url}/v2/tickers/{symbol}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as r:
                return json.loads(r.read().decode('utf-8')).get('result', {})
        except Exception:
            return {}

    def get_all_tickers(self):
        try:
            url = f"{self.base_url}/v2/tickers"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=6) as r:
                data = json.loads(r.read().decode('utf-8')).get('result', [])
                return {item['symbol']: item for item in data if 'symbol' in item}
        except Exception as e:
            print(f"[DELTA] Error getting tickers: {e}")
            return {}

    def get_candles(self, symbol, resolution='5m', limit=65):
        try:
            now = int(time.time())
            step_sec = 3 * 60 if resolution == '3m' else (15 * 60 if resolution == '15m' else 5 * 60)
            start = now - limit * step_sec
            url = f"{self.base_url}/v2/history/candles?resolution={resolution}&symbol={symbol}&start={start}&end={now}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = json.loads(r.read().decode('utf-8')).get('result', [])
                return sorted(raw, key=lambda x: x['time'])
        except Exception as e:
            print(f"[DELTA] Candle error {symbol}: {e}")
            return []

    def get_balance(self):
        if self.paper_mode or not (self.api_key and self.api_secret):
            return self.portfolio.get("virtual_balance", config.VIRTUAL_INITIAL_BALANCE)
        try:
            res = self._api_request("GET", "/v2/wallet/balances")
            result = res.get("result", [])
            usd_rate = getattr(config, 'USD_TO_INR', 89.0)
            for b in result:
                asset = b.get("asset_symbol", "")
                available = float(b.get("available_balance", 0) or 0)
                if asset in ["INR", "INR_D"]:
                    return available
                if asset in ["USD", "USDT"]:
                    return available * usd_rate
            return self.portfolio.get("virtual_balance", config.VIRTUAL_INITIAL_BALANCE)
        except Exception:
            return self.portfolio.get("virtual_balance", config.VIRTUAL_INITIAL_BALANCE)

    def is_in_cooldown(self, symbol):
        cd_map = self.portfolio.get("cooldowns", {})
        now = time.time()
        expiry = cd_map.get(symbol, 0)
        if now < expiry:
            rem = int((expiry - now) / 60) + 1
            return True, rem
        try:
            import ai_advisor
            is_susp, susp_msg = ai_advisor.is_coin_suspended(symbol)
            if is_susp:
                return True, 240
        except Exception:
            pass
        return False, 0

    def open_position(self, symbol, entry_price, sl_price, signal_score, whale_info, side='LONG', targets=None):
        """
        GOLDEN POCKET EXECUTION ENGINE:
        - Strict Fixed Position Sizing (Render-Identical)
        - Strict SL Clamping (1.5% - 2.5% max)
        - Slippage Guard against bad testnet orderbooks
        - Integer contract sizing + Risk shield
        - Active SL orderbook confirmation + Emergency Bailout
        """
        # 1. SLIPPAGE GUARD (Anti-Bad-Fill Guard)
        max_slippage = getattr(config, 'MAX_SLIPPAGE_PCT', 0.005)
        try:
            ticker_data = self.get_ticker(symbol)
            quotes = ticker_data.get('quotes', {})
            best_ask = float(quotes.get('best_ask') or 0)
            best_bid = float(quotes.get('best_bid') or 0)
            
            if side == 'LONG' and best_ask > 0 and entry_price > 0:
                slippage_pct = (best_ask - entry_price) / entry_price
                if slippage_pct > max_slippage:
                    print(f"  [SLIPPAGE GUARD] Spread too wide for {symbol}! Mark: {entry_price}, Best Ask: {best_ask} (+{slippage_pct*100:.2f}% > {max_slippage*100:.1f}%). Order skipped to protect execution price!")
                    return None
            elif side == 'SHORT' and best_bid > 0 and entry_price > 0:
                slippage_pct = (entry_price - best_bid) / entry_price
                if slippage_pct > max_slippage:
                    print(f"  [SLIPPAGE GUARD] Spread too wide for {symbol}! Mark: {entry_price}, Best Bid: {best_bid} (-{slippage_pct*100:.2f}% > {max_slippage*100:.1f}%). Order skipped to protect execution price!")
                    return None
        except Exception as e:
            pass

        # 2. STRICT SL DISTANCE CLAMP (Guarantees SL is never far away!)
        if side == 'LONG':
            max_sl_price = entry_price * (1.0 - config.MAX_SL_PCT)
            min_sl_price = entry_price * (1.0 - config.MIN_SL_PCT)
            sl_price = max(max_sl_price, min(min_sl_price, sl_price))
        else:
            max_sl_price = entry_price * (1.0 + config.MAX_SL_PCT)
            min_sl_price = entry_price * (1.0 + config.MIN_SL_PCT)
            sl_price = min(max_sl_price, max(min_sl_price, sl_price))

        # 3. STRICT POSITION SIZING (Fixed INR 5,000 Budget with AI Psychology Multiplier)
        if getattr(config, 'USE_FIXED_POSITION_SIZE', True):
            base_size_inr = getattr(config, 'FIXED_POSITION_SIZE_INR', 5000.0)
            try:
                import ai_advisor
                size_mult = ai_advisor.get_position_size_multiplier()
            except Exception:
                size_mult = 1.0
            position_size_inr = base_size_inr * size_mult
            max_allowed_inr = getattr(config, 'MAX_POSITION_SIZE_INR', 6000.0)
        else:
            capital_inr = self.get_balance()
            risk_amount_inr = capital_inr * config.RISK_PER_TRADE_PCT
            sl_pct = abs(entry_price - sl_price) / entry_price if entry_price > 0 else config.STOP_LOSS_PCT
            sl_pct = max(config.MIN_SL_PCT, min(config.MAX_SL_PCT, sl_pct))
            position_size_inr = risk_amount_inr / sl_pct
            max_allowed_inr = (capital_inr * config.LEVERAGE) / config.MAX_CONCURRENT_TRADES
            position_size_inr = min(position_size_inr, max_allowed_inr)

        usd_rate = getattr(config, 'USD_TO_INR', 89.0)
        position_size_usd = position_size_inr / usd_rate

        prod_info = self.cached_products.get(symbol, {})
        product_id = prod_info.get("id")
        c_val_str = prod_info.get("contract_value", "1.0") or "1.0"
        tick_size_str = prod_info.get("tick_size", "0.01")
        try:
            c_val = float(c_val_str)
        except Exception:
            c_val = 1.0

        unit_curr = prod_info.get("contract_unit_currency", "")
        one_contract_usd = c_val if unit_curr == "USD" else c_val * entry_price
        one_contract_inr = one_contract_usd * usd_rate

        max_allowed_single_contract_inr = min(position_size_inr * 1.35, max_allowed_inr)
        if one_contract_inr > max_allowed_single_contract_inr:
            print(f"  [RISK SHIELD] ⚠️ REJECTED {symbol}: 1 contract value (₹{one_contract_inr:,.0f}) exceeds position budget (₹{position_size_inr:,.0f})!")
            return None

        contracts = int(round(position_size_usd / one_contract_usd)) if one_contract_usd > 0 else 0
        if contracts < 1:
            if one_contract_inr <= max_allowed_single_contract_inr:
                contracts = 1
            else:
                return None

        if contracts * one_contract_inr > max_allowed_inr and one_contract_inr > 0:
            contracts = int(max_allowed_inr / one_contract_inr)
            if contracts < 1:
                return None

        contracts = int(contracts)
        exact_size_usd = contracts * one_contract_usd
        exact_size_inr = exact_size_usd * usd_rate

        entry_rounded_str = round_to_tick(entry_price, tick_size_str)
        sl_rounded_str = round_to_tick(sl_price, tick_size_str)
        actual_fill_price = float(entry_rounded_str)
        sl_rounded = float(sl_rounded_str)

        # ----------------------------------------------------
        # LIVE DELTA API EXECUTION WITH FILL & SL VERIFICATION
        # ----------------------------------------------------
        order_res = {}
        sl_order_id = None
        if not self.paper_mode and self.api_key and self.api_secret and product_id:
            api_side = "buy" if side == "LONG" else "sell"
            
            # Primary: Native Bracket Order
            payload = {
                "product_id": int(product_id),
                "product_symbol": symbol,
                "size": int(contracts),
                "side": api_side,
                "order_type": "market_order",
                "bracket_stop_loss_price": sl_rounded_str,
                "bracket_stop_trigger_method": "mark_price"
            }
            order_res = self._api_request("POST", "/v2/orders", payload_dict=payload)

            if "error" in order_res or not order_res.get("success", False):
                # Fallback: Market Entry + Standalone Reduce-Only SL Order
                market_payload = {
                    "product_id": int(product_id),
                    "product_symbol": symbol,
                    "size": int(contracts),
                    "side": api_side,
                    "order_type": "market_order"
                }
                order_res = self._api_request("POST", "/v2/orders", payload_dict=market_payload)
                if "error" in order_res or not order_res.get("success", False):
                    print(f"  [DELTA API ERROR] Entry rejected: {order_res}")
                    return None

                # Attach Stop-Loss immediately
                sl_side = "sell" if side == "LONG" else "buy"
                sl_payload = {
                    "product_id": int(product_id),
                    "product_symbol": symbol,
                    "size": int(contracts),
                    "side": sl_side,
                    "order_type": "market_order",
                    "stop_order_type": "stop_loss_order",
                    "stop_price": sl_rounded_str,
                    "stop_trigger_method": "mark_price",
                    "reduce_only": True
                }
                sl_res = self._api_request("POST", "/v2/orders", payload_dict=sl_payload)
                sl_order_id = sl_res.get("result", {}).get("id")

                # 🛡️ EMERGENCY FAIL-SAFE: If Stop-Loss failed to attach, CLOSE POSITION IMMEDIATELY!
                if not sl_res.get("success", False):
                    print(f"  [CRITICAL SAFETY TRIGGERED] Stop-Loss attachment failed! Emergency closing {symbol}...")
                    close_payload = {
                        "product_id": int(product_id),
                        "product_symbol": symbol,
                        "size": int(contracts),
                        "side": sl_side,
                        "order_type": "market_order"
                    }
                    self._api_request("POST", "/v2/orders", payload_dict=close_payload)
                    return None

            # Capture actual execution fill price from exchange
            fill_data = order_res.get("result", {})
            if fill_data.get("average_fill_price"):
                actual_fill_price = float(fill_data["average_fill_price"])

        pos = {
            "symbol": symbol,
            "side": side,
            "entry_time": time.time(),
            "entry_price": actual_fill_price,
            "current_price": actual_fill_price,
            "sl_price": sl_rounded,
            "initial_sl": sl_rounded,
            "product_id": product_id,
            "contracts": contracts,
            "contracts_remaining": contracts,
            "one_contract_usd": one_contract_usd,
            "one_contract_inr": one_contract_inr,
            "size_inr": exact_size_inr,
            "size_usd": exact_size_usd,
            "units_remaining": 1.0,
            "leverage": config.LEVERAGE,
            "micro_be_hit": False,
            "tp1_hit": False,
            "tp2_hit": False,
            "tp3_hit": False,
            "highest_gain_pct": 0.0,
            "realized_pnl_inr": 0.0,
            "realized_pnl": 0.0,
            "score": signal_score,
            "whale_info": whale_info,
            "api_order_id": order_res.get("result", {}).get("id"),
            "sl_order_id": sl_order_id
        }
        if targets and isinstance(targets, dict):
            pos["fib_tp1_gain_pct"] = targets.get("tp1_gain_pct")
            pos["fib_tp2_gain_pct"] = targets.get("tp2_gain_pct")
            pos["fib_tp3_gain_pct"] = targets.get("tp3_gain_pct")
            pos["tp1_price"] = targets.get("tp1_price")
            pos["tp2_price"] = targets.get("tp2_price")
            pos["tp3_price"] = targets.get("tp3_price")
            pos["macro_high"] = targets.get("macro_high")
            pos["macro_low"] = targets.get("macro_low")
        self.portfolio["open_positions"][symbol] = pos
        self.save_portfolio()
        return pos

    open_paper_position = open_position

    def update_stop_loss(self, symbol, new_sl_price):
        if symbol not in self.portfolio["open_positions"]:
            return False
        prod_info = self.cached_products.get(symbol, {})
        tick_size_str = prod_info.get("tick_size", "0.01")
        sl_rounded = float(round_to_tick(new_sl_price, tick_size_str))
        self.portfolio["open_positions"][symbol]["sl_price"] = sl_rounded
        self.save_portfolio()

        if not self.paper_mode and self.api_key and self.api_secret:
            pos = self.portfolio["open_positions"][symbol]
            product_id = pos.get("product_id")
            side = pos.get("side", "LONG")
            sl_side = "sell" if side == "LONG" else "buy"
            contracts = pos.get("contracts_remaining", pos.get("contracts", 1))

            sl_payload = {
                "product_id": int(product_id),
                "product_symbol": symbol,
                "size": int(contracts),
                "side": sl_side,
                "order_type": "market_order",
                "stop_order_type": "stop_loss_order",
                "stop_price": str(sl_rounded),
                "stop_trigger_method": "mark_price",
                "reduce_only": True
            }
            res = self._api_request("POST", "/v2/orders", payload_dict=sl_payload)
            return res.get("success", False)
        return True

    def close_position(self, symbol, exit_price, reason):
        if symbol not in self.portfolio["open_positions"]:
            return {}
        pos = self.portfolio["open_positions"][symbol]
        entry = pos["entry_price"]
        side = pos.get("side", "LONG")
        usd_rate = getattr(config, 'USD_TO_INR', 89.0)

        gain_pct = (exit_price - entry) / entry if side == "LONG" else (entry - exit_price) / entry
        units_left = pos.get("units_remaining", 1.0)
        pos_size = pos.get("size_inr", getattr(config, 'FIXED_POSITION_SIZE_INR', 5000.0))
        final_leg_pnl = pos_size * units_left * gain_pct
        total_pnl = final_leg_pnl + pos.get("realized_pnl_inr", 0.0)

        self.portfolio["virtual_balance"] += final_leg_pnl
        self.portfolio["realized_pnl"] += final_leg_pnl

        # Dynamic Rolling Cooldown: If trade took a loss (stop loss hit / choppy day), cool down for 2.5 hours.
        # If it was a win, normal 45m cooldown is plenty!
        loss_cd = getattr(config, 'SL_HIT_COOLDOWN_MINUTES', 150)
        norm_cd = getattr(config, 'NORMAL_COOLDOWN_MINUTES', 45)
        cd_minutes = loss_cd if final_leg_pnl < 0 else norm_cd
        if "cooldowns" not in self.portfolio:
            self.portfolio["cooldowns"] = {}
        self.portfolio["cooldowns"][symbol] = time.time() + (cd_minutes * 60)

        record = {
            "symbol": symbol,
            "side": side,
            "entry_time": pos["entry_time"],
            "exit_time": time.time(),
            "entry_price": entry,
            "exit_price": exit_price,
            "gain_pct": gain_pct,
            "realized_pnl_inr": total_pnl,
            "reason": reason
        }
        self.portfolio["trade_history"].append(record)
        del self.portfolio["open_positions"][symbol]
        self.save_portfolio()

        # 🧠 Smart Money Psychology & AI Advisor Post-Mortem Hook
        try:
            import ai_advisor
            ai_advisor.record_trade_exit(record, self, config)
        except Exception as e:
            print(f"⚠️ [AI ADVISOR POST-MORTEM ERROR]: {e}")

        # Live Delta API Market Exit
        if not self.paper_mode and self.api_key and self.api_secret:
            product_id = pos.get("product_id")
            close_side = "sell" if side == "LONG" else "buy"
            contracts = pos.get("contracts_remaining", pos.get("contracts", 1))
            payload = {
                "product_id": int(product_id),
                "product_symbol": symbol,
                "size": int(contracts),
                "side": close_side,
                "order_type": "market_order"
            }
            self._api_request("POST", "/v2/orders", payload_dict=payload)

        return record

    close_paper_position = close_position
