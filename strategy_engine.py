import time
import math
import datetime
import config
from telegram_notifier import send_telegram_alert, get_now_ist_str
from whale_wallet_tracker import WhaleWalletTracker

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def calculate_ema(prices, period):
    if len(prices) < period:
        return prices[-1] if prices else 0
    k = 2.0 / (period + 1.0)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1.0 - k)
    return ema

def calculate_atr(candles, period=14):
    if len(candles) < period + 1:
        return 0.0
    tr_list = []
    for i in range(1, len(candles)):
        h = float(candles[i]['high'])
        l = float(candles[i]['low'])
        prev_c = float(candles[i-1]['close'])
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)
    return sum(tr_list[-period:]) / period if tr_list else 0.0

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]
    avg_gain = sum(gains[-period:]) / period if gains else 0.0001
    avg_loss = sum(losses[-period:]) / period if losses else 0.0001
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def get_binance_symbol(delta_symbol):
    clean = delta_symbol.replace('1000', '').replace('USD', '')
    return f"{clean}USDT"

class StrategyEngine:
    def __init__(self, delta_client, whale_feed):
        self.client = delta_client
        self.whale_feed = whale_feed
        self.wallet_tracker = WhaleWalletTracker()

    def evaluate_entry(self, symbol, ticker, delta_candles):
        """
        GOLDEN POCKET OTE REVERSAL SNIPER:
        1. Anti-Climax Guard: Strictly bans Longs if price > 4% above 1h low.
        2. Bottom Liquidity Sweep + EMA 10/20 Golden Cross.
        3. Fibonacci 0.50 - 0.618 OTE Retest Calculation.
        4. Structural Stop Loss strictly below Swing Low.
        """
        if symbol in self.client.portfolio["open_positions"]:
            return False, "NONE", 0, 0, 0, "Position already active"

        if len(self.client.portfolio["open_positions"]) >= config.MAX_CONCURRENT_TRADES:
            return False, "NONE", 0, 0, 0, "Max concurrent positions reached"

        turnover_24h = float(ticker.get("turnover_usd", 0) or 0)
        mark_price = float(ticker.get("mark_price", 0) or ticker.get("close", 0) or 0)
        if mark_price <= 0:
            return False, "NONE", 0, 0, 0, "Invalid mark price"

        if turnover_24h > 0 and turnover_24h < config.MIN_24H_VOLUME_USD:
            return False, "NONE", 0, 0, 0, f"Turnover below threshold (${turnover_24h:,.0f})"

        in_cd, rem_mins = self.client.is_in_cooldown(symbol)
        if in_cd:
            return False, "NONE", 0, 0, 0, f"Coin in 45m cooldown ({rem_mins}m left)"

        if len(delta_candles) < 30:
            return False, "NONE", 0, 0, 0, "Insufficient candle history"

        btc_ok, btc_msg = self.whale_feed.check_btc_safety()

        # ----------------------------------------------------
        # 🛡️ GATE 1: ANTI-CLIMAX GUARD (Anti-FOMO Peak Buying Ban!)
        # ----------------------------------------------------
        # Look back 12 candles (1 hour)
        past_12 = delta_candles[-12:]
        lowest_1h = min([float(c['low']) for c in past_12])
        highest_1h = max([float(c['high']) for c in past_12])

        pump_from_1h_low = (mark_price - lowest_1h) / lowest_1h if lowest_1h > 0 else 0
        dump_from_1h_high = (highest_1h - mark_price) / highest_1h if highest_1h > 0 else 0

        # Technical Indicators
        closes = [float(c['close']) for c in delta_candles]
        ema_10 = calculate_ema(closes, 10)
        ema_20 = calculate_ema(closes, 20)
        ema_50 = calculate_ema(closes, 50)
        rsi = calculate_rsi(closes, 14)

        prev_closes = closes[:-1]
        prev_ema_10 = calculate_ema(prev_closes, 10)
        prev_ema_20 = calculate_ema(prev_closes, 20)

        c_curr = delta_candles[-1]
        c_prev = delta_candles[-2]

        # Whale tracking confluence
        binance_symbol = get_binance_symbol(symbol)
        whale_profile = self.whale_feed.get_whale_profile(symbol)
        binance_gain = whale_profile.get('binance_gain', 0.0)
        w_score, w_bias, w_reason = self.wallet_tracker.evaluate_whale_influence(symbol, binance_symbol)

        delta_vols = [float(c.get('volume', 0)) for c in delta_candles[-20:-2] if float(c.get('volume', 0)) > 0]
        avg_vol = sum(delta_vols) / len(delta_vols) if delta_vols else 1.0

        # ----------------------------------------------------
        # 🟢 A. EVALUATE LONG SETUP (Early Reversal + Fib OTE)
        # ----------------------------------------------------
        # Anti-Climax Rule: If price already pumped > 4.0% from 1h low, NEVER buy Long!
        is_not_climax_long = (pump_from_1h_low <= config.ANTI_CLIMAX_MAX_PUMP_PCT)
        
        # EMA 10/20 Shift: EMA 10 crosses above EMA 20 OR was below and just crossed
        ema_bullish_shift = (ema_10 >= ema_20) and (prev_ema_10 <= prev_ema_20 or ema_10 > ema_50)

        # Bottom Sweep: Price touched near lowest_1h with lower wick rejection
        c_high = float(c_curr['high'])
        c_low = float(c_curr['low'])
        c_open = float(c_curr['open'])
        c_close = float(c_curr['close'])
        c_range = max(c_high - c_low, 0.000001)
        lower_wick = min(c_open, c_close) - c_low
        has_lower_rejection = (lower_wick / c_range >= 0.20) or (c_low <= lowest_1h * 1.005)

        if btc_ok and is_not_climax_long and ema_bullish_shift and rsi <= 65.0:
            # Measure displacement leg: Swing Low to Impulse High
            swing_low = lowest_1h
            impulse_high = max(c_high, float(c_prev['high']))
            leg_range = impulse_high - swing_low

            if leg_range > 0 and (impulse_high - swing_low) / swing_low >= 0.012: # At least 1.2% displacement
                fib_500 = impulse_high - config.FIB_ENTRY_MIN * leg_range
                fib_618 = impulse_high - config.FIB_ENTRY_MAX * leg_range
                # Golden Pocket Sweet Spot entry
                ote_entry = impulse_high - 0.559 * leg_range

                # Check if current price is in or near the Golden Pocket zone (within 0.8% of OTE)
                if abs(mark_price - ote_entry) / ote_entry <= 0.008 or mark_price <= fib_500:
                    entry_price = min(mark_price, ote_entry)
                    # Structural Stop Loss strictly below swing low, clamped to entry_price
                    raw_sl = swing_low * (1.0 - config.STRUCTURAL_SL_BUFFER_PCT)
                    sl_dist_pct = (entry_price - raw_sl) / entry_price if entry_price > 0 else config.STOP_LOSS_PCT

                    # Clamp SL between MIN_SL_PCT (1.5%) and MAX_SL_PCT (2.5%)
                    if sl_dist_pct > config.MAX_SL_PCT:
                        sl_price = entry_price * (1.0 - config.MAX_SL_PCT)
                    elif sl_dist_pct < config.MIN_SL_PCT:
                        sl_price = entry_price * (1.0 - config.MIN_SL_PCT)
                    else:
                        sl_price = raw_sl

                    reasons = [
                        "Bottom Liquidity Sweep Confirmed",
                        "EMA 10/20 Bullish Golden Shift",
                        f"Fib 0.50-0.618 Golden Pocket OTE Entry (${entry_price:.5f})",
                        f"Sheltered Swing Low SL ({abs(entry_price - sl_price)/entry_price*100:.2f}%)"
                    ]
                    if w_score > 0 and w_bias == "LONG":
                        reasons.append(w_reason)
                    return True, "LONG", entry_price, sl_price, 85, " | ".join(reasons)

        # ----------------------------------------------------
        # 🔴 B. EVALUATE SHORT SETUP (Early Top Reversal + Fib OTE)
        # ----------------------------------------------------
        if getattr(config, 'ENABLE_SHORTS', True):
            is_not_climax_short = (dump_from_1h_high <= config.ANTI_CLIMAX_MAX_DUMP_PCT)
            ema_bearish_shift = (ema_10 <= ema_20) and (prev_ema_10 >= prev_ema_20 or ema_10 < ema_50)
            upper_wick = c_high - max(c_open, c_close)
            has_upper_rejection = (upper_wick / c_range >= 0.20) or (c_high >= highest_1h * 0.995)

            if is_not_climax_short and ema_bearish_shift and rsi >= 35.0:
                swing_high = highest_1h
                impulse_low = min(c_low, float(c_prev['low']))
                leg_range = swing_high - impulse_low

                if leg_range > 0 and (swing_high - impulse_low) / swing_high >= 0.012:
                    fib_500 = impulse_low + config.FIB_ENTRY_MIN * leg_range
                    fib_618 = impulse_low + config.FIB_ENTRY_MAX * leg_range
                    ote_entry = impulse_low + 0.559 * leg_range

                    if abs(mark_price - ote_entry) / ote_entry <= 0.008 or mark_price >= fib_500:
                        entry_price = max(mark_price, ote_entry)
                        # Structural Stop Loss strictly above swing high, clamped to entry_price
                        raw_sl = swing_high * (1.0 + config.STRUCTURAL_SL_BUFFER_PCT)
                        sl_dist_pct = (raw_sl - entry_price) / entry_price if entry_price > 0 else config.STOP_LOSS_PCT

                        # Clamp SL between MIN_SL_PCT (1.5%) and MAX_SL_PCT (2.5%)
                        if sl_dist_pct > config.MAX_SL_PCT:
                            sl_price = entry_price * (1.0 + config.MAX_SL_PCT)
                        elif sl_dist_pct < config.MIN_SL_PCT:
                            sl_price = entry_price * (1.0 + config.MIN_SL_PCT)
                        else:
                            sl_price = raw_sl

                        reasons = [
                            "Top Liquidity Sweep Rejection",
                            "EMA 10/20 Bearish Death Shift",
                            f"Fib 0.50-0.618 Golden Pocket Short (${entry_price:.5f})",
                            f"Sheltered Swing High SL ({abs(sl_price - entry_price)/entry_price*100:.2f}%)"
                        ]
                        if w_score > 0 and w_bias == "SHORT":
                            reasons.append(w_reason)
                        return True, "SHORT", entry_price, sl_price, 85, " | ".join(reasons)

        return False, "NONE", 0, 0, 0, "No Golden Pocket setup"

    def manage_positions(self, current_tickers):
        """
        2-Tier Breakeven & Multi-Tier Fibonacci Extension Harvesting:
        - Micro-BE at +1.2% (Risk Free)
        - TP1 at +3.0% (Book 30%, lock SL to +1.5%)
        - TP2 at +5.5% (Book 40%, lock SL to +3.5%)
        - TP3 Runner at +9.0%+
        - 20-min Early Decay Cut (-1.5%)
        """
        open_pos = dict(self.client.portfolio["open_positions"])
        now = time.time()
        sym_curr = getattr(config, 'CURRENCY_SYMBOL', '₹')
        usd_rate = getattr(config, 'USD_TO_INR', 89.0)

        for symbol, pos in open_pos.items():
            ticker = current_tickers.get(symbol)
            if not ticker:
                continue

            current_price = float(ticker.get("mark_price", 0) or ticker.get("close", 0) or 0)
            if current_price <= 0:
                continue

            side = pos.get("side", "LONG")
            entry_price = pos["entry_price"]
            sl_price = pos["sl_price"]

            if side == "LONG":
                gain_pct = (current_price - entry_price) / entry_price
                hit_sl = (current_price <= sl_price)
            else:
                gain_pct = (entry_price - current_price) / entry_price
                hit_sl = (current_price >= sl_price)

            pos["current_price"] = current_price
            pos["highest_gain_pct"] = max(pos.get("highest_gain_pct", 0.0), gain_pct)
            trade_duration_mins = (now - pos.get("entry_time", now)) / 60.0

            b_tag = getattr(config, 'BOT_TAG', '')
            tag = f"{b_tag} {'PAPER' if config.PAPER_TRADING else 'LIVE'}"

            # ----------------------------------------------------
            # 1. STOP-LOSS CHECK
            # ----------------------------------------------------
            if hit_sl:
                reason = "Protected Profit / Breakeven Stop" if pos.get("micro_be_hit") else "Sheltered Swing Stop Hit"
                closed = self.client.close_paper_position(symbol, sl_price, reason)
                pnl_val = closed.get('realized_pnl_inr', closed.get('realized_pnl', 0.0))
                bal_val = self.client.portfolio.get('virtual_balance', config.VIRTUAL_INITIAL_BALANCE)
                msg = (
                    f"🛑 *{tag} EXIT [{side}]: {symbol}*\\n"
                    f"• Time (IST): *{get_now_ist_str()}*\\n"
                    f"• Reason: {reason}\\n"
                    f"• Exit Price: `${sl_price}`\\n"
                    f"• Realized PnL: *{'+' if pnl_val >= 0 else ''}{sym_curr}{pnl_val:,.2f}*\\n"
                    f"• Account Balance: *{sym_curr}{bal_val:,.2f}*"
                )
                send_telegram_alert(msg)
                continue

            # ----------------------------------------------------
            # 1b. EARLY MOMENTUM DECAY CUT (20-Min Rule @ -1.5%)
            # ----------------------------------------------------
            if getattr(config, 'ENABLE_EARLY_DECAY_CUT', True):
                if trade_duration_mins >= config.EARLY_CUT_MINUTES and not pos.get("micro_be_hit") and not pos.get("tp1_hit"):
                    if gain_pct <= config.EARLY_CUT_LOSS_PCT:
                        reason = f"Early Reversal Decay Cut ({trade_duration_mins:.0f}m @ {gain_pct*100:.1f}%)"
                        closed = self.client.close_paper_position(symbol, current_price, reason)
                        pnl_val = closed.get('realized_pnl_inr', closed.get('realized_pnl', 0.0))
                        bal_val = self.client.portfolio.get('virtual_balance', config.VIRTUAL_INITIAL_BALANCE)
                        msg = (
                            f"✂️ *{tag} EARLY LOSS CUT [{side}]: {symbol}*\\n"
                            f"• Time (IST): *{get_now_ist_str()}*\\n"
                            f"• Reason: Reversal stalled after {trade_duration_mins:.0f}m (Cut at {gain_pct*100:.1f}%)\\n"
                            f"• Exit Price: `${current_price}`\\n"
                            f"• Realized PnL: *{'+' if pnl_val >= 0 else ''}{sym_curr}{pnl_val:,.2f}*\\n"
                            f"• Capital Saved: *~50% saved vs full SL*\\n"
                            f"• Account Balance: *{sym_curr}{bal_val:,.2f}*"
                        )
                        send_telegram_alert(msg)
                        continue

            # ----------------------------------------------------
            # 2. TIME-STAGNATION EXIT (Flat after 90 mins)
            # ----------------------------------------------------
            if trade_duration_mins >= config.MAX_HOLD_MINUTES and not pos.get("tp1_hit"):
                if abs(gain_pct) < 0.015:
                    closed = self.client.close_paper_position(symbol, current_price, f"Time Stagnation ({trade_duration_mins:.0f}m)")
                    pnl_val = closed.get('realized_pnl_inr', closed.get('realized_pnl', 0.0))
                    bal_val = self.client.portfolio.get('virtual_balance', config.VIRTUAL_INITIAL_BALANCE)
                    msg = (
                        f"⏱️ *{tag} STAGNATION EXIT [{side}]: {symbol}*\\n"
                        f"• Time (IST): *{get_now_ist_str()}*\\n"
                        f"• Reason: Trade flat after 90 mins\\n"
                        f"• Realized PnL: *{'+' if pnl_val >= 0 else ''}{sym_curr}{pnl_val:,.2f}*\\n"
                        f"• Capital freed for fresh Golden Pocket setups!"
                    )
                    send_telegram_alert(msg)
                    continue

            # ----------------------------------------------------
            # 3. TIER-1 QUICK BREAKEVEN (+1.2% Gain): 100% Risk Free!
            # ----------------------------------------------------
            if not pos.get("micro_be_hit") and gain_pct >= config.MICRO_BE_TRIGGER_PCT:
                pos["micro_be_hit"] = True
                be_buf = config.MICRO_BE_BUFFER_PCT
                if side == "LONG":
                    pos["sl_price"] = entry_price * (1.0 + be_buf)
                else:
                    pos["sl_price"] = entry_price * (1.0 - be_buf)
                pos["locked_gain_pct"] = be_buf
                self.client.update_stop_loss(symbol, pos["sl_price"])
                msg = (
                    f"🛡️ *{tag} QUICK-SHIELD ACTIVATED [{side}]: {symbol} (+{gain_pct*100:.1f}%)*\\n"
                    f"• Time (IST): *{get_now_ist_str()}*\\n"
                    f"• Current Price: `${current_price}`\\n"
                    f"• New Stop-Loss: `${pos['sl_price']}` (Locked at +{be_buf*100:.2f}% buffer)\\n"
                    f"• Trade is now **100% RISK-FREE**!"
                )
                send_telegram_alert(msg)

            # ----------------------------------------------------
            # 4. TIER-2 PROFIT HARVEST: TP1 (+3.0% Gain) -> Book 30% Cash!
            # ----------------------------------------------------
            if not pos.get("tp1_hit") and gain_pct >= config.TP1_PCT:
                pos["tp1_hit"] = True
                tp1_ratio = config.TP1_BOOK_RATIO
                contracts = pos.get("contracts", 0)
                c_close = max(1, int(round(contracts * tp1_ratio)))
                pos["contracts_remaining"] = max(1, contracts - c_close)
                pos["units_remaining"] = pos["units_remaining"] * (1.0 - tp1_ratio)

                pnl_inr = pos.get("size_inr", 3571.0) * tp1_ratio * gain_pct
                pos["realized_pnl_inr"] = pos.get("realized_pnl_inr", 0.0) + pnl_inr
                self.client.portfolio["virtual_balance"] += pnl_inr
                self.client.portfolio["realized_pnl"] += pnl_inr

                # Lock SL to +1.5% guaranteed win
                if side == "LONG":
                    pos["sl_price"] = entry_price * 1.012
                else:
                    pos["sl_price"] = entry_price * (1.0 - 0.012)
                pos["locked_gain_pct"] = 0.012
                self.client.update_stop_loss(symbol, pos["sl_price"])

                msg = (
                    f"🎯 *{tag} TP1 HIT [{side}]: {symbol} (+{gain_pct*100:.1f}%)*\\n"
                    f"• Time (IST): *{get_now_ist_str()}*\\n"
                    f"• Cash Booked: *+{sym_curr}{pnl_inr:,.2f} (30% Position Banked)*\\n"
                    f"• SL Locked to: *+1.2% Guaranteed Win* (`${pos['sl_price']}`)\\n"
                    f"• Remaining 70% continues for Fib 1.618 Extension (+4.5%)!"
                )
                send_telegram_alert(msg)

            # ----------------------------------------------------
            # 5. TIER-3 PROFIT HARVEST: TP2 (+5.5% Fib 1.618) -> Book 40% Cash!
            # ----------------------------------------------------
            if pos.get("tp1_hit") and not pos.get("tp2_hit") and gain_pct >= config.TP2_PCT:
                pos["tp2_hit"] = True
                tp2_ratio = config.TP2_BOOK_RATIO
                contracts = pos.get("contracts", 0)
                c_close = max(1, int(round(contracts * tp2_ratio)))
                pos["contracts_remaining"] = max(1, pos.get("contracts_remaining", contracts) - c_close)
                pos["units_remaining"] = pos["units_remaining"] * (1.0 - tp2_ratio)

                pnl_inr = pos.get("size_inr", 3571.0) * tp2_ratio * gain_pct
                pos["realized_pnl_inr"] = pos.get("realized_pnl_inr", 0.0) + pnl_inr
                self.client.portfolio["virtual_balance"] += pnl_inr
                self.client.portfolio["realized_pnl"] += pnl_inr

                # Lock SL to +3.5% guaranteed win
                if side == "LONG":
                    pos["sl_price"] = entry_price * 1.030
                else:
                    pos["sl_price"] = entry_price * (1.0 - 0.030)
                pos["locked_gain_pct"] = 0.030
                self.client.update_stop_loss(symbol, pos["sl_price"])

                msg = (
                    f"🚀 *{tag} TP2 FIB 1.618 EXTENSION HIT [{side}]: {symbol} (+{gain_pct*100:.1f}%)*\\n"
                    f"• Time (IST): *{get_now_ist_str()}*\\n"
                    f"• Cash Booked: *+{sym_curr}{pnl_inr:,.2f} (Total 70% Banked)*\\n"
                    f"• SL Locked to: *+3.0% Super Lock* (`${pos['sl_price']}`)\\n"
                    f"• Remaining 30% RUNNER running for TP3 (+8.0%+)!"
                )
                send_telegram_alert(msg)

            # ----------------------------------------------------
            # 6. TIER-4 RUNNER TRAILING (Wide trailing for 30% runner)
            # ----------------------------------------------------
            if pos.get("tp2_hit"):
                # Ratchet SL behind peak gain
                trail_sl_dist = 0.018 # Wide 1.8% breathing room
                if gain_pct > (pos.get("locked_gain_pct", 0.035) + 0.005):
                    new_lock = gain_pct - trail_sl_dist
                    if new_lock > pos.get("locked_gain_pct", 0.035):
                        pos["locked_gain_pct"] = new_lock
                        if side == "LONG":
                            pos["sl_price"] = entry_price * (1.0 + new_lock)
                        else:
                            pos["sl_price"] = entry_price * (1.0 - new_lock)
                        self.client.update_stop_loss(symbol, pos["sl_price"])

            # ----------------------------------------------------
            # 7. TP3 MOONSHOT BLAST (+9.0%+)
            # ----------------------------------------------------
            if not pos.get("tp3_hit") and gain_pct >= config.TP3_PCT:
                pos["tp3_hit"] = True
                closed = self.client.close_paper_position(symbol, current_price, f"TP3 MEGA BLAST (+{gain_pct*100:.1f}%)")
                pnl_val = closed.get('realized_pnl_inr', closed.get('realized_pnl', 0.0))
                bal_val = self.client.portfolio.get('virtual_balance', config.VIRTUAL_INITIAL_BALANCE)
                msg = (
                    f"🔥 *{tag} TP3 MEGA BLAST JACKPOT [{side}]: {symbol} (+{gain_pct*100:.1f}%)*\\n"
                    f"• Time (IST): *{get_now_ist_str()}*\\n"
                    f"• Exit Price: `${current_price}`\\n"
                    f"• Final Trade PnL: *+{sym_curr}{pnl_val:,.2f}*\\n"
                    f"• Account Balance: *{sym_curr}{bal_val:,.2f}*"
                )
                send_telegram_alert(msg)
