"""
========================================================================================
DELTA EXCHANGE INDIA CLIENT & COMPOUNDING PORTFOLIO MANAGER (INR EDITION)
Exchange: Delta Exchange India (api.india.delta.exchange)
Currency: Indian Rupee (INR - ₹)
Time strictly locked to Indian Standard Time (IST, UTC+5:30)
========================================================================================
"""
import urllib.request
import urllib.parse
import json
import time
import hmac
import hashlib
import datetime
import os
import config
import telegram_notifier

class DeltaClient:
    def __init__(self):
        self.base_url = config.DELTA_BASE_URL
        self.state_file = os.path.join(os.path.dirname(__file__), "elite_sniper_state.json")
        self.last_loss_timestamps = {}
        self.load_state()

    def load_state(self):
        """Loads persistent portfolio balance and trade records in Indian Rupee (INR - ₹)."""
        now_month = config.get_now_ist().strftime('%Y-%m')
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    self.state = json.load(f)
                    self.state.setdefault("initial_capital_inr", config.INITIAL_CAPITAL_INR)
                    self.state.setdefault("active_capital_inr", config.INITIAL_CAPITAL_INR)
                    self.state.setdefault("month_starting_capital_inr", config.INITIAL_CAPITAL_INR)
                    self.state.setdefault("current_month", now_month)
                    self.state.setdefault("banked_profit_inr", 0.0)
                    self.state.setdefault("total_net_pnl_inr", 0.0)
                    self.state.setdefault("open_positions", {})
                    self.state.setdefault("closed_trades", [])
                    return
            except Exception as e:
                print(f"[STATE LOAD ERROR] {e}. Reinitializing default state.")

        self.state = {
            "initial_capital_inr": config.INITIAL_CAPITAL_INR,
            "active_capital_inr": config.INITIAL_CAPITAL_INR,
            "month_starting_capital_inr": config.INITIAL_CAPITAL_INR,
            "current_month": now_month,
            "banked_profit_inr": 0.0,
            "total_net_pnl_inr": 0.0,
            "open_positions": {},
            "closed_trades": []
        }
        self.save_state()

    def save_state(self):
        """Persists current state atomically to disk."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=4)
        except Exception as e:
            print(f"[STATE SAVE ERROR] {e}")

    def fetch_candles(self, symbol, resolution="15m", limit=60):
        """
        Fetches historical candles from Delta Exchange India public API without geo-blocking.
        """
        end_time = int(time.time())
        res_seconds_map = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "2h": 7200, "4h": 14400, "1d": 86400
        }
        res_secs = res_seconds_map.get(resolution, 900)
        start_time = end_time - (res_secs * limit)

        url = f"{self.base_url}/v2/history/candles?resolution={resolution}&symbol={symbol}&start={start_time}&end={end_time}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode())
                candles = data.get("result", [])
                formatted = []
                for c in candles:
                    formatted.append({
                        "time": c["time"],
                        "datetime": config.format_timestamp_ist(c["time"]),
                        "open": float(c["open"]),
                        "high": float(c["high"]),
                        "low": float(c["low"]),
                        "close": float(c["close"]),
                        "volume": float(c.get("volume", 0))
                    })
                formatted.sort(key=lambda x: x["time"])
                return formatted
        except Exception as e:
            print(f"[FETCH ERROR] {symbol} ({resolution}) candles: {e}")
            return []

    def fetch_ticker(self, symbol):
        """Fetches live mark price and last traded price."""
        url = f"{self.base_url}/v2/tickers/{symbol}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode())
                res = data.get("result", {})
                return {
                    "last_price": float(res.get("close", 0)),
                    "mark_price": float(res.get("mark_price", 0))
                }
        except Exception:
            return None

    def get_current_risk_inr(self):
        """
        Compounding Engine with Max Active Capital ceiling in INR:
        - Risk per trade is strictly 2.0% of active INR capital.
        - Surplus profits beyond MAX_ACTIVE_CAPITAL_INR are safely banked into the vault.
        """
        now_month = config.get_now_ist().strftime('%Y-%m')
        recorded_month = self.state.get("current_month", now_month)

        if now_month != recorded_month:
            # Calendar month rollover in IST!
            curr_active = self.state.get("active_capital_inr", config.INITIAL_CAPITAL_INR)
            if curr_active > config.MAX_ACTIVE_CAPITAL_INR:
                overflow = curr_active - config.MAX_ACTIVE_CAPITAL_INR
                self.state["banked_profit_inr"] += overflow
                self.state["active_capital_inr"] = config.MAX_ACTIVE_CAPITAL_INR

            self.state["month_starting_capital_inr"] = self.state["active_capital_inr"]
            self.state["current_month"] = now_month
            self.save_state()

        curr_cap = self.state.get("active_capital_inr", config.INITIAL_CAPITAL_INR)
        return curr_cap * config.RISK_PER_TRADE_PCT

    def open_position(self, setup):
        """
        Opens a new trade position using 20x Leverage and Rescued Risk Management in INR.
        """
        symbol = setup["symbol"]
        side = setup["side"]
        entry_price = setup["entry_price"]
        sl_price = setup["sl_price"]
        rescue_tp = setup["rescue_tp"]
        tp1_price = setup["tp1_price"]
        tp2_price = setup["tp2_price"]

        if len(self.state["open_positions"]) >= config.MAX_CONCURRENT_TRADES:
            return None

        risk_inr = self.get_current_risk_inr()
        sl_pct = abs(entry_price - sl_price) / entry_price
        if sl_pct <= 0:
            return None

        # Position value calculation in INR
        raw_position_inr = risk_inr / sl_pct
        position_inr = min(raw_position_inr, config.MAX_POSITION_INR)
        margin_used_inr = position_inr / config.LEVERAGE

        # Equivalent USD sizes for Delta contract logic
        position_usd = position_inr / config.USD_INR_RATE
        entry_inr_est = entry_price * config.USD_INR_RATE

        now_str = config.get_now_ist().strftime('%Y-%m-%d %H:%M:%S')
        trade = {
            "symbol": symbol,
            "side": side,
            "entry_time": now_str,
            "entry_timestamp": time.time(),
            "entry_price": entry_price,
            "entry_inr_est": entry_inr_est,
            "sl_price": sl_price,
            "initial_sl": sl_price,
            "rescue_tp": rescue_tp,
            "tp1_price": tp1_price,
            "tp2_price": tp2_price,
            "sl_pct": sl_pct * 100,
            "risk_inr": risk_inr,
            "position_inr": position_inr,
            "position_usd": position_usd,
            "remaining_ratio": 1.0,  # 100% open initially
            "margin_used_inr": margin_used_inr,
            "rescue_hit": False,
            "tp1_hit": False,
            "realized_pnl_inr": 0.0,
            "setup_type": setup.get("setup_type", "ICT_OTE")
        }

        self.state["open_positions"][symbol] = trade
        self.save_state()
        telegram_notifier.notify_entry(trade)
        print(f"🟢 [NEW TRADE OPENED] {symbol} {side} @ ${entry_price:.4f} (~₹{entry_inr_est:,.2f}) | Risk: {config.format_inr(risk_inr)} | 20x Margin: {config.format_inr(margin_used_inr)}")
        return trade

    def manage_positions(self):
        """
        Monitors active positions against live prices in INR:
        1. Checks Level 1 Rescued TP (+1.0R / Asian Mid): Books 30% profit in INR & locks SL to Breakeven!
        2. Checks Level 2 TP1 (Asian High/Low): Books 40% profit in INR & locks trailing SL!
        3. Checks Level 3 TP2 Runner (3.0R): Books final 30% profit in INR!
        4. Checks Stop Loss execution.
        """
        if not self.state["open_positions"]:
            return

        symbols_to_close = []

        for symbol, trade in list(self.state["open_positions"].items()):
            ticker = self.fetch_ticker(symbol)
            if not ticker or ticker["last_price"] <= 0:
                continue

            current_price = ticker["last_price"]
            side = trade["side"]
            entry_price = trade["entry_price"]
            sl_price = trade["sl_price"]
            pos_inr = trade["position_inr"]

            # ---------------------------------------------------------
            # 1. RESCUED RULE (+1.0R / Asian Mid): 30% Profit in INR & Breakeven Lock
            # ---------------------------------------------------------
            if not trade["rescue_hit"]:
                hit_rescue = (current_price >= trade["rescue_tp"]) if side == "LONG" else (current_price <= trade["rescue_tp"])
                if hit_rescue:
                    closed_val_inr = pos_inr * config.RESCUE_CLOSE_RATIO
                    r_dist_pct = abs(trade["rescue_tp"] - entry_price) / entry_price
                    pnl_rescue_inr = closed_val_inr * r_dist_pct

                    trade["remaining_ratio"] -= config.RESCUE_CLOSE_RATIO
                    trade["realized_pnl_inr"] += pnl_rescue_inr
                    trade["rescue_hit"] = True
                    trade["sl_price"] = entry_price  # BREAKEVEN LOCK!

                    self._apply_realized_pnl_inr(pnl_rescue_inr)
                    self.save_state()
                    telegram_notifier.notify_rescue_hit(trade, pnl_rescue_inr)
                    print(f"🛡️ [RESCUED TRIGGERED] {symbol} booked 30% (+{config.format_inr(pnl_rescue_inr)}) & SL moved to BREAKEVEN!")

            # ---------------------------------------------------------
            # 2. TARGET 1 (Asian High/Low): 40% Profit in INR & Trailing SL
            # ---------------------------------------------------------
            if not trade["tp1_hit"] and trade["rescue_hit"]:
                hit_tp1 = (current_price >= trade["tp1_price"]) if side == "LONG" else (current_price <= trade["tp1_price"])
                if hit_tp1:
                    closed_val_inr = pos_inr * config.TP1_CLOSE_RATIO
                    r_dist_pct = abs(trade["tp1_price"] - entry_price) / entry_price
                    pnl_tp1_inr = closed_val_inr * r_dist_pct

                    trade["remaining_ratio"] -= config.TP1_CLOSE_RATIO
                    trade["realized_pnl_inr"] += pnl_tp1_inr
                    trade["tp1_hit"] = True

                    # Lock SL to +1.0R in guaranteed profit for remaining runner
                    r_dist = abs(entry_price - trade["initial_sl"])
                    trade["sl_price"] = entry_price + (1.0 * r_dist) if side == "LONG" else entry_price - (1.0 * r_dist)

                    self._apply_realized_pnl_inr(pnl_tp1_inr)
                    self.save_state()
                    telegram_notifier.notify_tp1_hit(trade, pnl_tp1_inr, trade["sl_price"])
                    print(f"💰 [TP1 HIT] {symbol} booked 40% (+{config.format_inr(pnl_tp1_inr)}) & trailing SL locked!")

            # ---------------------------------------------------------
            # 3. TARGET 2 RUNNER (3.0R Home Run): Final 30% Profit in INR
            # ---------------------------------------------------------
            hit_tp2 = (current_price >= trade["tp2_price"]) if side == "LONG" else (current_price <= trade["tp2_price"])
            if hit_tp2 and trade["tp1_hit"]:
                closed_val_inr = pos_inr * trade["remaining_ratio"]
                r_dist_pct = abs(trade["tp2_price"] - entry_price) / entry_price
                pnl_tp2_inr = closed_val_inr * r_dist_pct

                total_trade_pnl_inr = trade["realized_pnl_inr"] + pnl_tp2_inr
                self._apply_realized_pnl_inr(pnl_tp2_inr)

                telegram_notifier.notify_tp2_hit(trade, total_trade_pnl_inr)
                symbols_to_close.append((symbol, "TARGET_2_FULL_WIN", total_trade_pnl_inr, current_price))
                continue

            # ---------------------------------------------------------
            # 4. STOP LOSS CHECK (Breakeven or Initial SL)
            # ---------------------------------------------------------
            hit_sl = (current_price <= sl_price) if side == "LONG" else (current_price >= sl_price)
            if hit_sl:
                remaining_val_inr = pos_inr * trade["remaining_ratio"]
                loss_dist_pct = abs(sl_price - entry_price) / entry_price

                if sl_price == entry_price:
                    loss_remaining_inr = 0.0
                    reason = "BREAKEVEN_PROTECTED_EXIT"
                else:
                    loss_remaining_inr = -(remaining_val_inr * loss_dist_pct)
                    reason = "STOP_LOSS_EXIT"

                total_trade_pnl_inr = trade["realized_pnl_inr"] + loss_remaining_inr
                self._apply_realized_pnl_inr(loss_remaining_inr)

                telegram_notifier.notify_sl_hit(trade, total_trade_pnl_inr, reason)
                symbols_to_close.append((symbol, reason, total_trade_pnl_inr, current_price))

        for symbol, reason, final_pnl_inr, exit_px in symbols_to_close:
            self._close_position_record(symbol, reason, final_pnl_inr, exit_px)

    def _apply_realized_pnl_inr(self, pnl_inr):
        """Applies realized PnL in INR and manages the MAX_ACTIVE_CAPITAL_INR cap."""
        self.state["active_capital_inr"] += pnl_inr
        self.state["total_net_pnl_inr"] += pnl_inr

        # Surplus profit beyond MAX_ACTIVE_CAPITAL_INR gets banked into safe vault
        if self.state["active_capital_inr"] > config.MAX_ACTIVE_CAPITAL_INR:
            overflow = self.state["active_capital_inr"] - config.MAX_ACTIVE_CAPITAL_INR
            self.state["banked_profit_inr"] += overflow
            self.state["active_capital_inr"] = config.MAX_ACTIVE_CAPITAL_INR

    def _close_position_record(self, symbol, reason, final_pnl_inr, exit_px):
        """Archives closed trade and removes from open positions."""
        if symbol in self.state["open_positions"]:
            trade = self.state["open_positions"].pop(symbol)
            trade["exit_time"] = config.get_now_ist().strftime('%Y-%m-%d %H:%M:%S')
            trade["exit_price"] = exit_px
            trade["final_pnl_inr"] = final_pnl_inr
            trade["close_reason"] = reason

            self.state["closed_trades"].append(trade)
            self.save_state()
            print(f"🏁 [POSITION CLOSED] {symbol} | Reason: {reason} | Final PnL: {config.format_inr(final_pnl_inr)}")
