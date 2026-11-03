"""
========================================================================================
DELTA EXCHANGE INDIA CLIENT & COMPOUNDING PORTFOLIO MANAGER (INR EDITION)
Exchange: Delta Exchange India (api.india.delta.exchange)
Currency: Indian Rupee (INR - ₹)
Integer Contract Rounding: Guaranteed Zero Rejection on Partial / Full Exits
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
        self.contract_values = dict(getattr(config, 'CONTRACT_VALUES', {}))
        self.active_universe = list(getattr(config, 'SYMBOLS', []))
        self.bstock_symbols = set()
        self.last_screener_refresh = 0
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

    def fetch_product_specs(self):
        """
        Fetches all perpetual futures specs from Delta Exchange India:
        - Maps contract_value (lot size) for exact Integer Contract Rounding.
        - Identifies non-24/7 equity bStock tokens to exclude them from crypto universe.
        """
        url = f"{self.base_url}/v2/products"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        bstock_symbols = set()
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                data = json.loads(r.read().decode())
                products = data.get("result", [])
                for p in products:
                    if p.get("contract_type") == "perpetual_futures":
                        sym = p.get("symbol")
                        try:
                            cv = float(p.get("contract_value", 1.0))
                            self.contract_values[sym] = cv
                        except (ValueError, TypeError):
                            pass
                        desc = p.get("description", "")
                        if "bStocks" in desc:
                            bstock_symbols.add(sym)
            self.bstock_symbols = bstock_symbols
            print(f"📦 [PRODUCTS] Cached lot sizes for {len(self.contract_values)} products ({len(bstock_symbols)} bStocks filtered).")
        except Exception as e:
            print(f"[PRODUCT SPECS ERROR] {e}")
        return bstock_symbols

    def fetch_dynamic_top_universe(self, limit=None, min_volume_usd=None, max_spread_pct=None):
        """
        DYNAMIC INSTITUTIONAL SCREENER (240+ COIN AUTO-FILTER):
        Executes 1 single bulk API request to /v2/tickers:
        - Automatically filters out dead / illiquid coins (< min_volume_usd)
        - Automatically filters out wide-spread traps (> max_spread_pct)
        - Excludes non-24/7 equity tokens (bStocks)
        - Always preserves core staple coins (SOL, DOGE, BTC, ETH, ADA, AVAX, BNB)
        - Sorts remaining coins by 24h turnover to pick top liquid movers
        - Caches contract values dynamically for zero-rejection integer lot sizing
        """
        if limit is None:
            limit = getattr(config, 'DYNAMIC_UNIVERSE_LIMIT', 25)
        if min_volume_usd is None:
            min_volume_usd = getattr(config, 'DYNAMIC_MIN_VOLUME_USD', 500000.0)
        if max_spread_pct is None:
            max_spread_pct = getattr(config, 'DYNAMIC_MAX_SPREAD_PCT', 0.0020)

        core_staples = getattr(config, 'CORE_STAPLES', ['SOLUSD', 'DOGEUSD', 'BTCUSD', 'ETHUSD', 'ADAUSD', 'AVAXUSD', 'BNBUSD'])

        # Refresh product lot size specs if needed
        if not self.bstock_symbols or len(self.contract_values) < 20:
            self.fetch_product_specs()

        url = f"{self.base_url}/v2/tickers"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        candidates = []

        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                data = json.loads(r.read().decode())
                tickers = data.get("result", [])

            for t in tickers:
                if t.get("contract_type") != "perpetual_futures":
                    continue

                symbol = t.get("symbol")
                if not symbol or symbol in self.bstock_symbols:
                    continue

                try:
                    cv = float(t.get("contract_value", 1.0))
                    self.contract_values[symbol] = cv
                except (ValueError, TypeError):
                    pass

                turnover = float(t.get("turnover_usd") or 0)
                quotes = t.get("quotes") or {}
                try:
                    bid = float(quotes.get("best_bid") or 0)
                    ask = float(quotes.get("best_ask") or 0)
                except (ValueError, TypeError):
                    bid, ask = 0, 0

                spread_pct = ((ask - bid) / ask) if ask > 0 and bid > 0 else 1.0
                mark_price = float(t.get("mark_price") or 0)

                if turnover >= min_volume_usd and spread_pct <= max_spread_pct and mark_price > 0:
                    candidates.append({
                        "symbol": symbol,
                        "turnover": turnover,
                        "spread_pct": spread_pct * 100,
                        "mark_price": mark_price,
                        "contract_value": self.contract_values.get(symbol, 1.0)
                    })

            # Sort by 24h turnover descending
            candidates.sort(key=lambda x: x["turnover"], reverse=True)

            universe = []
            # 1. Guarantee core staples
            for s in core_staples:
                if s in self.contract_values or any(c["symbol"] == s for c in candidates):
                    universe.append(s)

            # 2. Fill up to limit with top active coins
            for c in candidates:
                if c["symbol"] not in universe:
                    universe.append(c["symbol"])
                if len(universe) >= limit:
                    break

            self.active_universe = universe
            self.last_screener_refresh = time.time()
            print(f"🔥 [DYNAMIC SCREENER] Selected Top {len(universe)} Liquid Coins from 240+ Delta universe.")
            return universe

        except Exception as e:
            print(f"[SCREENER FETCH ERROR] {e}. Keeping current universe.")
            return self.active_universe

    def get_current_risk_inr(self):
        """
        Compounding Engine with Max Active Capital ceiling in INR:
        - Risk per trade is strictly 2.5% of active INR capital.
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

    def calculate_integer_exit_contracts(self, total_contracts):
        """
        INTEGER CONTRACT ROUNDING ENGINE FOR DELTA EXCHANGE INDIA:
        Guarantees that 60% / 25% / 15% partial exits are strictly whole integer lots.
        Prevents Delta Exchange API rejection: 'contract_size must be an integer'.
        Sum of exit_1 + exit_2 + exit_3 ALWAYS equals total_contracts exactly!
        """
        if total_contracts >= 4:
            exit_1 = max(1, int(round(total_contracts * 0.60)))
            exit_2 = max(1, int(round(total_contracts * 0.25)))
            exit_3 = total_contracts - exit_1 - exit_2
            if exit_3 < 0:
                exit_2 += exit_3
                exit_3 = 0
        elif total_contracts == 3:
            exit_1 = 2  # 66%
            exit_2 = 1  # 33%
            exit_3 = 0
        elif total_contracts == 2:
            exit_1 = 1  # 50%
            exit_2 = 1  # 50%
            exit_3 = 0
        else: # total_contracts == 1
            exit_1 = 0  # 1 full contract rides to TP1 with Breakeven Plus locked!
            exit_2 = 1
            exit_3 = 0
        return int(exit_1), int(exit_2), int(exit_3)

    def open_position(self, setup):
        """
        Opens a new trade position using 20x Leverage and Integer Contract Rounding.
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

        # Integer contract sizing for Delta Exchange India
        contract_mult = self.contract_values.get(symbol, getattr(config, 'CONTRACT_VALUES', {}).get(symbol, 1.0))
        contract_unit_usd = entry_price * contract_mult

        curr_active_cap = self.state.get("active_capital_inr", config.INITIAL_CAPITAL_INR)
        
        # Margin buffer check: Ensure at least ₹400 free balance remains before taking trade
        total_margin_used = sum(p.get("margin_used_inr", 0) for p in self.state["open_positions"].values())
        free_capital = curr_active_cap - total_margin_used
        if free_capital < 400.0:
            print(f"⚠️ [MARGIN BUFFER] Free capital ({config.format_inr(free_capital)}) is below minimum buffer (₹400). Skipping {symbol}.")
            return None

        # STRICT FIXED SIZING: Fixed ₹9,000 - ₹10,000 per trade (Compounding STOPPED)
        # Position size will NEVER exceed ₹10,000 INR regardless of capital or tight SL
        target_pos_inr = getattr(config, 'TARGET_POSITION_INR', 9500.0)
        max_pos_inr = getattr(config, 'MAX_POSITION_INR', 10000.0)
        
        target_pos_usd = target_pos_inr / config.USD_INR_RATE
        raw_contracts = target_pos_usd / contract_unit_usd
        total_contracts = max(1, int(round(raw_contracts)))

        # Hard guard: If integer contract rounding exceeds MAX_POSITION_INR (₹10,000), round down
        actual_position_usd = total_contracts * contract_unit_usd
        actual_position_inr = actual_position_usd * config.USD_INR_RATE
        if total_contracts > 1 and actual_position_inr > max_pos_inr:
            total_contracts = max(1, int(target_pos_usd // contract_unit_usd))
            actual_position_usd = total_contracts * contract_unit_usd
            actual_position_inr = actual_position_usd * config.USD_INR_RATE

        # Calculate exact integer contract exits (30% / 40% / 30%)
        exit_1_contracts, exit_2_contracts, exit_3_contracts = self.calculate_integer_exit_contracts(total_contracts)

        margin_used_inr = actual_position_inr / config.LEVERAGE
        entry_inr_est = entry_price * config.USD_INR_RATE
        actual_risk_inr = actual_position_inr * sl_pct

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
            "risk_inr": actual_risk_inr,
            "position_inr": actual_position_inr,
            "position_usd": actual_position_usd,
            "total_contracts": total_contracts,
            "remaining_contracts": total_contracts,
            "exit_1_contracts": exit_1_contracts,
            "exit_2_contracts": exit_2_contracts,
            "exit_3_contracts": exit_3_contracts,
            "remaining_ratio": 1.0,
            "margin_used_inr": margin_used_inr,
            "rescue_hit": False,
            "tp1_hit": False,
            "realized_pnl_inr": 0.0,
            "setup_type": setup.get("setup_type", "ICT_OTE")
        }

        self.state["open_positions"][symbol] = trade
        self.save_state()
        telegram_notifier.notify_entry(trade)
        print(f"🟢 [NEW TRADE OPENED] {symbol} {side} @ ${entry_price:.4f} (~₹{entry_inr_est:,.2f}) | Contracts: {total_contracts} [L1:{exit_1_contracts}, L2:{exit_2_contracts}, L3:{exit_3_contracts}] | Margin: {config.format_inr(margin_used_inr)}")
        return trade

    def manage_positions(self):
        """
        Monitors active positions with Integer Contract Partial Exits:
        1. Level 1 (+1.0R / Asian Mid): Closes exit_1_contracts & locks SL to Breakeven!
        2. Level 2 TP1 (Asian High/Low): Closes exit_2_contracts & locks trailing SL!
        3. Level 3 TP2 Runner (3.0R): Closes all remaining contracts!
        4. Stop Loss execution.
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
            total_c = max(1, trade.get("total_contracts", 1))

            # ---------------------------------------------------------
            # 1. RESCUED RULE (+1.0R / Asian Mid): Integer Contract Exit + Breakeven Lock
            # ---------------------------------------------------------
            if not trade["rescue_hit"]:
                hit_rescue = (current_price >= trade["rescue_tp"]) if side == "LONG" else (current_price <= trade["rescue_tp"])
                if hit_rescue:
                    exit_contracts = trade.get("exit_1_contracts", 0)

                    if exit_contracts > 0:
                        closed_ratio = exit_contracts / total_c
                        closed_val_inr = pos_inr * closed_ratio
                        r_dist_pct = abs(trade["rescue_tp"] - entry_price) / entry_price
                        pnl_rescue_inr = closed_val_inr * r_dist_pct

                        trade["remaining_contracts"] = max(0, trade.get("remaining_contracts", total_c) - exit_contracts)
                        trade["remaining_ratio"] = trade["remaining_contracts"] / total_c
                        trade["realized_pnl_inr"] += pnl_rescue_inr
                        self._apply_realized_pnl_inr(pnl_rescue_inr)
                    else:
                        pnl_rescue_inr = 0.0

                    trade["rescue_hit"] = True
                    # BREAKEVEN PLUS: Set Stop Loss slightly above entry in guaranteed profit!
                    r_dist = abs(entry_price - trade["initial_sl"])
                    be_plus_buffer = getattr(config, 'BREAKEVEN_PLUS_R', 0.15) * r_dist
                    trade["sl_price"] = (entry_price + be_plus_buffer) if side == "LONG" else (entry_price - be_plus_buffer)

                    self.save_state()
                    telegram_notifier.notify_rescue_hit(trade, pnl_rescue_inr)
                    print(f"🛡️ [RESCUED TRIGGERED] {symbol} closed {exit_contracts} contract(s) (+{config.format_inr(pnl_rescue_inr)}) & SL locked at BREAKEVEN PLUS (${trade['sl_price']:.4f})!")

            # ---------------------------------------------------------
            # 2. TARGET 1 (Asian High/Low): Integer Contract Exit + Trailing SL
            # ---------------------------------------------------------
            if not trade["tp1_hit"] and trade["rescue_hit"]:
                hit_tp1 = (current_price >= trade["tp1_price"]) if side == "LONG" else (current_price <= trade["tp1_price"])
                if hit_tp1:
                    exit_contracts = trade.get("exit_2_contracts", 0)
                    closed_ratio = (exit_contracts / total_c) if exit_contracts > 0 else config.TP1_CLOSE_RATIO
                    closed_val_inr = pos_inr * closed_ratio
                    r_dist_pct = abs(trade["tp1_price"] - entry_price) / entry_price
                    pnl_tp1_inr = closed_val_inr * r_dist_pct

                    trade["remaining_contracts"] = max(0, trade.get("remaining_contracts", total_c) - exit_contracts)
                    trade["remaining_ratio"] = trade["remaining_contracts"] / total_c
                    trade["realized_pnl_inr"] += pnl_tp1_inr
                    trade["tp1_hit"] = True

                    # Lock SL to +1.0R in guaranteed profit for remaining runner
                    r_dist = abs(entry_price - trade["initial_sl"])
                    trade["sl_price"] = entry_price + (1.0 * r_dist) if side == "LONG" else entry_price - (1.0 * r_dist)

                    self._apply_realized_pnl_inr(pnl_tp1_inr)
                    self.save_state()
                    telegram_notifier.notify_tp1_hit(trade, pnl_tp1_inr, trade["sl_price"])
                    print(f"💰 [TP1 HIT] {symbol} closed {exit_contracts} contract(s) (+{config.format_inr(pnl_tp1_inr)}) & trailing SL locked!")

            # ---------------------------------------------------------
            # 3. TARGET 2 RUNNER (3.0R Home Run): Closes ALL Remaining Contracts
            # ---------------------------------------------------------
            hit_tp2 = (current_price >= trade["tp2_price"]) if side == "LONG" else (current_price <= trade["tp2_price"])
            if hit_tp2 and trade["tp1_hit"]:
                rem_c = trade.get("remaining_contracts", 0)
                closed_ratio = (rem_c / total_c) if rem_c > 0 else trade.get("remaining_ratio", 0.30)
                closed_val_inr = pos_inr * closed_ratio
                r_dist_pct = abs(trade["tp2_price"] - entry_price) / entry_price
                pnl_tp2_inr = closed_val_inr * r_dist_pct

                trade["remaining_contracts"] = 0
                trade["remaining_ratio"] = 0.0
                total_trade_pnl_inr = trade["realized_pnl_inr"] + pnl_tp2_inr
                self._apply_realized_pnl_inr(pnl_tp2_inr)

                telegram_notifier.notify_tp2_hit(trade, total_trade_pnl_inr)
                symbols_to_close.append((symbol, "TARGET_2_FULL_WIN", total_trade_pnl_inr, current_price))
                continue

            # ---------------------------------------------------------
            # 4. STOP LOSS CHECK (Breakeven Plus, Trailing SL or Initial SL)
            # ---------------------------------------------------------
            hit_sl = (current_price <= sl_price) if side == "LONG" else (current_price >= sl_price)
            if hit_sl:
                rem_c = trade.get("remaining_contracts", 0)
                closed_ratio = (rem_c / total_c) if rem_c > 0 else trade.get("remaining_ratio", 1.0)
                remaining_val_inr = pos_inr * closed_ratio
                trade["exit_price"] = sl_price

                # Check if SL is in profit (Trailing SL or Breakeven Plus) or in loss
                is_profit_sl = (sl_price > entry_price) if side == "LONG" else (sl_price < entry_price)
                if is_profit_sl:
                    pnl_dist_pct = abs(sl_price - entry_price) / entry_price
                    remaining_pnl_inr = remaining_val_inr * pnl_dist_pct
                    reason = "TRAILING_PROFIT_SL" if trade.get("tp1_hit") else "BREAKEVEN_PLUS_PROFIT_EXIT"
                elif sl_price == entry_price:
                    remaining_pnl_inr = 0.0
                    reason = "BREAKEVEN_PROTECTED_EXIT"
                else:
                    loss_dist_pct = abs(sl_price - entry_price) / entry_price
                    remaining_pnl_inr = -(remaining_val_inr * loss_dist_pct)
                    reason = "STOP_LOSS_EXIT"

                trade["remaining_contracts"] = 0
                trade["remaining_ratio"] = 0.0
                total_trade_pnl_inr = trade["realized_pnl_inr"] + remaining_pnl_inr
                self._apply_realized_pnl_inr(remaining_pnl_inr)

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
