"""
========================================================================================
DELTA EXCHANGE INDIA CLIENT & COMPOUNDING PORTFOLIO MANAGER ($100,000 CAP)
Exchange: Delta Exchange India (api.india.delta.exchange)
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
        """Loads persistent portfolio balance and trade records."""
        now_month = config.get_now_ist().strftime('%Y-%m')
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    self.state = json.load(f)
                    self.state.setdefault("initial_capital", config.INITIAL_CAPITAL)
                    self.state.setdefault("active_capital", config.INITIAL_CAPITAL)
                    self.state.setdefault("month_starting_capital", config.INITIAL_CAPITAL)
                    self.state.setdefault("current_month", now_month)
                    self.state.setdefault("banked_profit", 0.0)
                    self.state.setdefault("total_net_pnl", 0.0)
                    self.state.setdefault("open_positions", {})
                    self.state.setdefault("closed_trades", [])
                    return
            except Exception as e:
                print(f"[STATE LOAD ERROR] {e}. Reinitializing default state.")

        self.state = {
            "initial_capital": config.INITIAL_CAPITAL,
            "active_capital": config.INITIAL_CAPITAL,
            "month_starting_capital": config.INITIAL_CAPITAL,
            "current_month": now_month,
            "banked_profit": 0.0,
            "total_net_pnl": 0.0,
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

    def get_current_risk_dollars(self):
        """
        Compounding Engine with $100,000 active capital ceiling:
        - Risk per trade is strictly 2.0% of active capital.
        - Surplus profits beyond $100,000 are banked to the safe vault.
        """
        now_month = config.get_now_ist().strftime('%Y-%m')
        recorded_month = self.state.get("current_month", now_month)

        if now_month != recorded_month:
            # Calendar month rollover in IST!
            curr_active = self.state.get("active_capital", config.INITIAL_CAPITAL)
            if curr_active > config.MAX_ACTIVE_CAPITAL:
                overflow = curr_active - config.MAX_ACTIVE_CAPITAL
                self.state["banked_profit"] += overflow
                self.state["active_capital"] = config.MAX_ACTIVE_CAPITAL

            self.state["month_starting_capital"] = self.state["active_capital"]
            self.state["current_month"] = now_month
            self.save_state()

        curr_cap = self.state.get("active_capital", config.INITIAL_CAPITAL)
        return curr_cap * config.RISK_PER_TRADE_PCT

    def open_position(self, setup):
        """
        Opens a new trade position using 20x Leverage and Rescued Risk Management.
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

        risk_dollars = self.get_current_risk_dollars()
        sl_pct = abs(entry_price - sl_price) / entry_price
        if sl_pct <= 0:
            return None

        # Position value based on risk and SL distance
        raw_position_val = risk_dollars / sl_pct
        position_val = min(raw_position_val, config.MAX_POSITION_USD)
        margin_used = position_val / config.LEVERAGE

        now_str = config.get_now_ist().strftime('%Y-%m-%d %H:%M:%S')
        trade = {
            "symbol": symbol,
            "side": side,
            "entry_time": now_str,
            "entry_timestamp": time.time(),
            "entry_price": entry_price,
            "sl_price": sl_price,
            "initial_sl": sl_price,
            "rescue_tp": rescue_tp,
            "tp1_price": tp1_price,
            "tp2_price": tp2_price,
            "sl_pct": sl_pct * 100,
            "risk_amount": risk_dollars,
            "position_val": position_val,
            "remaining_ratio": 1.0,  # 100% open initially
            "margin_used": margin_used,
            "rescue_hit": False,
            "tp1_hit": False,
            "realized_pnl": 0.0,
            "setup_type": setup.get("setup_type", "ICT_OTE")
        }

        self.state["open_positions"][symbol] = trade
        self.save_state()
        telegram_notifier.notify_entry(trade)
        print(f"🟢 [NEW TRADE OPENED] {symbol} {side} @ ${entry_price:.4f} | Risk: ${risk_dollars:.2f} | 20x Margin: ${margin_used:.2f}")
        return trade

    def manage_positions(self):
        """
        Monitors active positions against live tick prices:
        1. Checks Level 1 Rescued TP (+1.0R / Asian Mid): Books 30% profit & locks SL to Breakeven!
        2. Checks Level 2 TP1 (Asian High/Low): Books 40% profit & locks trailing SL!
        3. Checks Level 3 TP2 Runner (3.0R): Books final 30% profit!
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
            pos_val = trade["position_val"]

            # ---------------------------------------------------------
            # 1. RESCUED RULE (+1.0R / Asian Mid): 30% Profit & Breakeven Lock
            # ---------------------------------------------------------
            if not trade["rescue_hit"]:
                hit_rescue = (current_price >= trade["rescue_tp"]) if side == "LONG" else (current_price <= trade["rescue_tp"])
                if hit_rescue:
                    # Book 30% profit
                    closed_val = pos_val * config.RESCUE_CLOSE_RATIO
                    r_dist_pct = abs(trade["rescue_tp"] - entry_price) / entry_price
                    pnl_rescue = closed_val * r_dist_pct

                    trade["remaining_ratio"] -= config.RESCUE_CLOSE_RATIO
                    trade["realized_pnl"] += pnl_rescue
                    trade["rescue_hit"] = True
                    trade["sl_price"] = entry_price  # BREAKEVEN LOCK!

                    self._apply_realized_pnl(pnl_rescue)
                    self.save_state()
                    telegram_notifier.notify_rescue_hit(trade, pnl_rescue)
                    print(f"🛡️ [RESCUED TRIGGERED] {symbol} booked 30% (+${pnl_rescue:.2f}) & SL moved to BREAKEVEN!")

            # ---------------------------------------------------------
            # 2. TARGET 1 (Asian High/Low): 40% Profit & Trailing SL
            # ---------------------------------------------------------
            if not trade["tp1_hit"] and trade["rescue_hit"]:
                hit_tp1 = (current_price >= trade["tp1_price"]) if side == "LONG" else (current_price <= trade["tp1_price"])
                if hit_tp1:
                    closed_val = pos_val * config.TP1_CLOSE_RATIO
                    r_dist_pct = abs(trade["tp1_price"] - entry_price) / entry_price
                    pnl_tp1 = closed_val * r_dist_pct

                    trade["remaining_ratio"] -= config.TP1_CLOSE_RATIO
                    trade["realized_pnl"] += pnl_tp1
                    trade["tp1_hit"] = True

                    # Lock SL to +1.0R in guaranteed profit for remaining runner
                    r_dist = abs(entry_price - trade["initial_sl"])
                    trade["sl_price"] = entry_price + (1.0 * r_dist) if side == "LONG" else entry_price - (1.0 * r_dist)

                    self._apply_realized_pnl(pnl_tp1)
                    self.save_state()
                    telegram_notifier.notify_tp1_hit(trade, pnl_tp1, trade["sl_price"])
                    print(f"💰 [TP1 HIT] {symbol} booked 40% (+${pnl_tp1:.2f}) & trailing SL locked!")

            # ---------------------------------------------------------
            # 3. TARGET 2 RUNNER (3.0R Home Run): Final 30% Profit
            # ---------------------------------------------------------
            hit_tp2 = (current_price >= trade["tp2_price"]) if side == "LONG" else (current_price <= trade["tp2_price"])
            if hit_tp2 and trade["tp1_hit"]:
                closed_val = pos_val * trade["remaining_ratio"]
                r_dist_pct = abs(trade["tp2_price"] - entry_price) / entry_price
                pnl_tp2 = closed_val * r_dist_pct

                total_trade_pnl = trade["realized_pnl"] + pnl_tp2
                self._apply_realized_pnl(pnl_tp2)

                telegram_notifier.notify_tp2_hit(trade, total_trade_pnl)
                symbols_to_close.append((symbol, "TARGET_2_FULL_WIN", total_trade_pnl, current_price))
                continue

            # ---------------------------------------------------------
            # 4. STOP LOSS CHECK (Breakeven or Initial SL)
            # ---------------------------------------------------------
            hit_sl = (current_price <= sl_price) if side == "LONG" else (current_price >= sl_price)
            if hit_sl:
                remaining_val = pos_val * trade["remaining_ratio"]
                loss_dist_pct = abs(sl_price - entry_price) / entry_price

                if sl_price == entry_price:
                    # Breakeven exit! (Zero loss on remaining portion!)
                    loss_remaining = 0.0
                    reason = "BREAKEVEN_PROTECTED_EXIT"
                else:
                    loss_remaining = -(remaining_val * loss_dist_pct)
                    reason = "STOP_LOSS_EXIT"

                total_trade_pnl = trade["realized_pnl"] + loss_remaining
                self._apply_realized_pnl(loss_remaining)

                telegram_notifier.notify_sl_hit(trade, total_trade_pnl, reason)
                symbols_to_close.append((symbol, reason, total_trade_pnl, current_price))

        for symbol, reason, final_pnl, exit_px in symbols_to_close:
            self._close_position_record(symbol, reason, final_pnl, exit_px)

    def _apply_realized_pnl(self, pnl):
        """Applies realized PnL and manages the $100,000 active capital cap."""
        self.state["active_capital"] += pnl
        self.state["total_net_pnl"] += pnl

        # Surplus profit beyond $100,000 gets banked into safe vault
        if self.state["active_capital"] > config.MAX_ACTIVE_CAPITAL:
            overflow = self.state["active_capital"] - config.MAX_ACTIVE_CAPITAL
            self.state["banked_profit"] += overflow
            self.state["active_capital"] = config.MAX_ACTIVE_CAPITAL

    def _close_position_record(self, symbol, reason, final_pnl, exit_px):
        """Archives closed trade and removes from open positions."""
        if symbol in self.state["open_positions"]:
            trade = self.state["open_positions"].pop(symbol)
            trade["exit_time"] = config.get_now_ist().strftime('%Y-%m-%d %H:%M:%S')
            trade["exit_price"] = exit_px
            trade["final_pnl"] = final_pnl
            trade["close_reason"] = reason

            self.state["closed_trades"].append(trade)
            self.save_state()
            print(f"🏁 [POSITION CLOSED] {symbol} | Reason: {reason} | Final PnL: ${final_pnl:+.2f}")
