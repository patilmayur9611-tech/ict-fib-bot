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

    def evaluate_entry(self, symbol, ticker, delta_candles, macro_candles=None):
        """
        GOLDEN POCKET OTE REVERSAL SNIPER:
        1. Anti-Climax Guard: Strictly bans Longs if price > 4% above 1h low.
        2. Bottom Liquidity Sweep + EMA 10/20 Golden Cross.
        3. Fibonacci 0.50 - 0.618 OTE Retest Calculation.
        4. Structural Stop Loss strictly below Swing Low.
        """
        if symbol in self.client.portfolio["open_positions"]:
            return False, "NONE", 0, 0, 0, "Position already active", None

        open_pos = self.client.portfolio["open_positions"]
        max_total = getattr(config, 'MAX_TOTAL_POSITIONS', 4)
        if len(open_pos) >= max_total:
            return False, "NONE", 0, 0, 0, f"Max total positions ({max_total}) reached", None

        if getattr(config, 'FREE_SLOT_ON_TP1', True):
            # Only count positions that still carry initial downside risk (TP1 not yet hit)
            active_risk_pos = [s for s, p in open_pos.items() if not p.get("tp1_hit")]
            max_active_risk = getattr(config, 'MAX_ACTIVE_RISK_TRADES', getattr(config, 'MAX_CONCURRENT_TRADES', 2))
            if len(active_risk_pos) >= max_active_risk:
                return False, "NONE", 0, 0, 0, f"Max active risk slots ({max_active_risk}) occupied", None
        else:
            if len(open_pos) >= config.MAX_CONCURRENT_TRADES:
                return False, "NONE", 0, 0, 0, "Max concurrent positions reached", None

        turnover_24h = float(ticker.get("turnover_usd", 0) or 0)
        mark_price = float(ticker.get("mark_price", 0) or ticker.get("close", 0) or 0)
        if mark_price <= 0:
            return False, "NONE", 0, 0, 0, "Invalid mark price", None

        if turnover_24h > 0 and turnover_24h < config.MIN_24H_VOLUME_USD:
            return False, "NONE", 0, 0, 0, f"Turnover below threshold (${turnover_24h:,.0f})", None

        in_cd, rem_mins = self.client.is_in_cooldown(symbol)
        if in_cd:
            return False, "NONE", 0, 0, 0, f"Coin in 45m cooldown ({rem_mins}m left)", None

        if len(delta_candles) < 30:
            return False, "NONE", 0, 0, 0, "Insufficient candle history", None

        btc_ok, btc_msg = self.whale_feed.check_btc_safety()

        # ----------------------------------------------------
        # 🌐 MULTI-TIMEFRAME MACRO STRUCTURE & ANTI-CLIMAX
        # ----------------------------------------------------
        if macro_candles and len(macro_candles) >= 12:
            m_win = macro_candles[-16:] if len(macro_candles) >= 16 else macro_candles
        else:
            m_win = delta_candles[-16:] if len(delta_candles) >= 16 else delta_candles

        macro_low = min([float(c['low']) for c in m_win])
        macro_high = max([float(c['high']) for c in m_win])
        macro_leg = macro_high - macro_low
        macro_disp = macro_leg / macro_low if macro_low > 0 else 0

        lowest_1h = macro_low
        highest_1h = macro_high

        pump_from_1h_low = (mark_price - macro_low) / macro_low if macro_low > 0 else 0
        dump_from_1h_high = (macro_high - mark_price) / macro_high if macro_high > 0 else 0

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

        # 🌐 4-Pillar Institutional Intelligence Feed (Binance Futures)
        intel = None
        if getattr(config, 'ENABLE_INSTITUTIONAL_FEEDS', False) and hasattr(self.whale_feed, 'get_institutional_intelligence'):
            try:
                intel = self.whale_feed.get_institutional_intelligence(symbol, mark_price)
            except Exception:
                intel = None

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
        macro_ok_long = (ema_20 >= ema_50) if getattr(config, 'ENABLE_MACRO_TREND_FILTER', False) else True

        if btc_ok and macro_ok_long and is_not_climax_long and ema_bullish_shift and rsi <= 65.0:
            # Measure displacement leg: Swing Low to Impulse High across 1-hour window
            swing_low = lowest_1h
            impulse_high = highest_1h
            leg_range = impulse_high - swing_low

            min_disp = getattr(config, 'MIN_DISPLACEMENT_LEG_PCT', 0.012)

            if leg_range > 0 and (impulse_high - swing_low) / swing_low >= min_disp:
                fib_500 = impulse_high - config.FIB_ENTRY_MIN * leg_range
                fib_618 = impulse_high - config.FIB_ENTRY_MAX * leg_range
                # Golden Pocket Sweet Spot entry
                ote_entry = impulse_high - 0.559 * leg_range

                # Check if current price is in or near the Golden Pocket zone (within 0.8% of OTE)
                if abs(mark_price - ote_entry) / ote_entry <= 0.010 or (mark_price <= fib_500 and mark_price >= swing_low):
                    # --- 🌐 INSTITUTIONAL CONFLUENCE FILTER (LONG) ---
                    if intel:
                        # Funding Rate Flush Filter (Bans Longs if retail longs are hyper-leveraged)
                        fr = intel.get('funding_rate', 0.0)
                        max_long_fr = getattr(config, 'LONG_FLUSH_FUNDING_THRESHOLD', 0.00050)
                        if fr >= max_long_fr:
                            return False, "NONE", 0, 0, 0, f"Rejected: Extreme Long Overleverage / Flush Risk (Funding: {fr*100:.3f}% >= {max_long_fr*100:.2f}%)", None

                        t_ratio = intel.get('taker_ratio', 1.0)
                        min_t = getattr(config, 'MIN_TAKER_BUY_RATIO_LONG', 0.90)
                        if t_ratio < min_t:
                            return False, "NONE", 0, 0, 0, f"Rejected: Taker Sell Dumping (Ratio: {t_ratio:.2f} < {min_t})", None

                        top_long = intel.get('top_long_pct', 0.50)
                        min_long = getattr(config, 'MIN_TOP_TRADER_LONG_PCT', 0.45)
                        if top_long < min_long:
                            return False, "NONE", 0, 0, 0, f"Rejected: Top Whales Net Short ({top_long*100:.1f}% Long < {min_long*100:.0f}%)", None

                        ask_w = intel.get('ask_wall')
                        if ask_w and ask_w.get('dist_pct', 1.0) < 0.006:
                            return False, "NONE", 0, 0, 0, f"Rejected: Overhead Resistance Wall at +{ask_w['dist_pct']*100:.2f}% (${ask_w['usd']/1e6:.1f}M)", None

                    entry_price = min(mark_price, ote_entry)
                    # Tight 3m Sheltered Stop Loss below recent local low (strictly 0.6% - 0.9% max!)
                    local_3m_low = min([float(c['low']) for c in delta_candles[-10:]])
                    raw_sl = local_3m_low * 0.9985
                    sl_dist_pct = (entry_price - raw_sl) / entry_price if entry_price > 0 else config.STOP_LOSS_PCT
                    sl_pct = max(config.MIN_SL_PCT, min(config.MAX_SL_PCT, sl_dist_pct))
                    sl_price = entry_price * (1.0 - sl_pct)

                    # 🎯 Trend-Based Fibonacci Extension Targets (anchored from 15m/5m Macro Structure)
                    tp1_p = macro_high # Macro High Retest
                    tp1_g = max(0.012, (tp1_p - entry_price) / entry_price)
                    tp2_p = entry_price + 1.272 * macro_leg # Fib 1.272 Extension
                    tp2_g = max(0.022, (tp2_p - entry_price) / entry_price)
                    tp3_p = entry_price + 1.618 * macro_leg # Fib 1.618 Golden Extension
                    tp3_g = max(0.035, (tp3_p - entry_price) / entry_price)

                    targets = {
                        "tp1_price": tp1_p,
                        "tp1_gain_pct": tp1_g,
                        "tp2_price": tp2_p,
                        "tp2_gain_pct": tp2_g,
                        "tp3_price": tp3_p,
                        "tp3_gain_pct": tp3_g,
                        "macro_high": macro_high,
                        "macro_low": macro_low
                    }

                    reasons = [
                        "3m Sniper Golden Pocket Retest",
                        "EMA 10/20 Bullish Golden Shift",
                        f"Entry (${entry_price:.5f}) | Tight 3m SL ({sl_pct*100:.2f}% = -₹{5000*sl_pct:.1f} max)",
                        f"Macro Fib TP1: +{tp1_g*100:.2f}% | Fib TP2: +{tp2_g*100:.2f}%"
                    ]
                    if intel:
                        sq_bias = intel.get('squeeze_bias', 'NEUTRAL')
                        fr = intel.get('funding_rate', 0.0)
                        if sq_bias == 'SHORT_SQUEEZE':
                            reasons.append(f"⚡ SHORT SQUEEZE FUEL (Funding: {fr*100:.3f}% | Trapped Shorts Paying Longs)")
                        reasons.append(f"Institutional Flow: Taker {intel.get('taker_ratio', 1.0):.2f}x | Whales {intel.get('top_long_pct', 0.5)*100:.0f}% Long | OI {intel.get('oi_status', 'NEUTRAL')}")
                        bid_w = intel.get('bid_wall')
                        if bid_w:
                            reasons.append(f"Supported by ${bid_w['usd']/1e6:.1f}M Bid Wall at -{bid_w['dist_pct']*100:.2f}%")
                    signal_score = 85
                    if lower_wick / c_range >= 0.35:
                        signal_score += 5
                        reasons.append("⚡ Smart Money Liquidity Sweep (Retail SL Hunt Swept)")

                    import ai_advisor
                    req_score = ai_advisor.get_required_entry_score()
                    p_state = ai_advisor.get_psychology_state()
                    if signal_score < req_score:
                        return False, "NONE", 0, 0, 0, f"Rejected: Score {signal_score} < Required {req_score} (AI {p_state} Discipline)", None

                    if w_score > 0 and w_bias == "LONG":
                        reasons.append(w_reason)
                    return True, "LONG", entry_price, sl_price, signal_score, " | ".join(reasons), targets

        # ----------------------------------------------------
        # 🔴 B. EVALUATE SHORT SETUP (Early Top Reversal + Fib OTE)
        # ----------------------------------------------------
        if getattr(config, 'ENABLE_SHORTS', True):
            is_not_climax_short = (dump_from_1h_high <= config.ANTI_CLIMAX_MAX_DUMP_PCT)
            ema_bearish_shift = (ema_10 <= ema_20) and (prev_ema_10 >= prev_ema_20 or ema_10 < ema_50)
            upper_wick = c_high - max(c_open, c_close)
            macro_ok_short = (ema_20 <= ema_50) if getattr(config, 'ENABLE_MACRO_TREND_FILTER', False) else True

            if is_not_climax_short and macro_ok_short and ema_bearish_shift and rsi >= 35.0:
                swing_high = highest_1h
                impulse_low = lowest_1h
                leg_range = swing_high - impulse_low

                min_disp = getattr(config, 'MIN_DISPLACEMENT_LEG_PCT', 0.012)

                if leg_range > 0 and (swing_high - impulse_low) / swing_high >= min_disp:
                    fib_500 = impulse_low + config.FIB_ENTRY_MIN * leg_range
                    fib_618 = impulse_low + config.FIB_ENTRY_MAX * leg_range
                    ote_entry = impulse_low + 0.559 * leg_range

                    if abs(mark_price - ote_entry) / ote_entry <= 0.010 or (mark_price >= fib_500 and mark_price <= swing_high):
                        # --- 🌐 INSTITUTIONAL CONFLUENCE FILTER (SHORT) ---
                        if getattr(config, 'STRICT_SHORT_BTC_TREND_FILTER', True) and btc_ok:
                            # If Bitcoin is Bullish / Stable, strictly avoid counter-trend altcoin shorts!
                            return False, "NONE", 0, 0, 0, f"Rejected: BTC is Bullish ({btc_msg}) - Counter-Trend Shorts Banned", None

                        if intel:
                            sq_bias = intel.get('squeeze_bias', 'NEUTRAL')
                            fr = intel.get('funding_rate', 0.0)
                            min_sq = getattr(config, 'SHORT_SQUEEZE_FUNDING_THRESHOLD', -0.00015)
                            if sq_bias == 'SHORT_SQUEEZE' or fr <= min_sq:
                                return False, "NONE", 0, 0, 0, f"Rejected: Short Squeeze Alert (Funding: {fr*100:.3f}% - Trapped Shorts Facing Squeeze)", None

                            t_ratio = intel.get('taker_ratio', 1.0)
                            max_t = getattr(config, 'MAX_TAKER_BUY_RATIO_SHORT', 0.85)
                            if t_ratio > max_t:
                                return False, "NONE", 0, 0, 0, f"Rejected: Taker Buy Pumping (Ratio: {t_ratio:.2f} > {max_t})", None

                            top_long = intel.get('top_long_pct', 0.50)
                            max_top = getattr(config, 'MAX_TOP_TRADER_LONG_FOR_SHORT', 0.48)
                            if top_long > max_top:
                                return False, "NONE", 0, 0, 0, f"Rejected: Top Whales Net Long ({top_long*100:.1f}% Long > {max_top*100:.0f}%)", None

                            bid_w = intel.get('bid_wall')
                            if bid_w and bid_w.get('dist_pct', 1.0) < 0.006:
                                return False, "NONE", 0, 0, 0, f"Rejected: Support Bid Wall at -{bid_w['dist_pct']*100:.2f}% (${bid_w['usd']/1e6:.1f}M)", None

                        entry_price = max(mark_price, ote_entry)
                        # Tight 3m Sheltered Stop Loss above recent local high (strictly 0.6% - 0.9% max!)
                        local_3m_high = max([float(c['high']) for c in delta_candles[-10:]])
                        raw_sl = local_3m_high * 1.0015
                        sl_dist_pct = (raw_sl - entry_price) / entry_price if entry_price > 0 else config.STOP_LOSS_PCT
                        sl_pct = max(config.MIN_SL_PCT, min(config.MAX_SL_PCT, sl_dist_pct))
                        sl_price = entry_price * (1.0 + sl_pct)

                        # 🎯 Trend-Based Fibonacci Extension Targets (anchored from 15m/5m Macro Structure)
                        tp1_p = macro_low # Macro Low Retest
                        tp1_g = max(0.012, (entry_price - tp1_p) / entry_price)
                        tp2_p = entry_price - 1.272 * macro_leg # Fib 1.272 Extension
                        tp2_g = max(0.022, (entry_price - tp2_p) / entry_price)
                        tp3_p = entry_price - 1.618 * macro_leg # Fib 1.618 Golden Extension
                        tp3_g = max(0.035, (entry_price - tp3_p) / entry_price)

                        targets = {
                            "tp1_price": tp1_p,
                            "tp1_gain_pct": tp1_g,
                            "tp2_price": tp2_p,
                            "tp2_gain_pct": tp2_g,
                            "tp3_price": tp3_p,
                            "tp3_gain_pct": tp3_g,
                            "macro_high": macro_high,
                            "macro_low": macro_low
                        }

                        reasons = [
                            "3m Top Rejection Sniper",
                            "EMA 10/20 Bearish Death Shift",
                            f"Short Entry (${entry_price:.5f}) | Tight 3m SL ({sl_pct*100:.2f}% = -₹{5000*sl_pct:.1f} max)",
                            f"Macro Fib TP1: +{tp1_g*100:.2f}% | Fib TP2: +{tp2_g*100:.2f}%"
                        ]
                        if intel:
                            reasons.append(f"Institutional Flow: Taker {intel.get('taker_ratio', 1.0):.2f}x | Whales {(1.0-intel.get('top_long_pct', 0.5))*100:.0f}% Short | OI {intel.get('oi_status', 'NEUTRAL')}")
                            ask_w = intel.get('ask_wall')
                            if ask_w:
                                reasons.append(f"Capped by ${ask_w['usd']/1e6:.1f}M Ask Wall at +{ask_w['dist_pct']*100:.2f}%")
                        signal_score = 85
                        if upper_wick / c_range >= 0.35:
                            signal_score += 5
                            reasons.append("⚡ Smart Money Liquidity Sweep (Breakout Traders Trapped)")

                        import ai_advisor
                        req_score = ai_advisor.get_required_entry_score()
                        p_state = ai_advisor.get_psychology_state()
                        if signal_score < req_score:
                            return False, "NONE", 0, 0, 0, f"Rejected: Score {signal_score} < Required {req_score} (AI {p_state} Discipline)", None

                        if w_score > 0 and w_bias == "SHORT":
                            reasons.append(w_reason)
                        return True, "SHORT", entry_price, sl_price, signal_score, " | ".join(reasons), targets

        return False, "NONE", 0, 0, 0, "No Golden Pocket setup", None

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

        dt_now = datetime.datetime.now(IST)
        is_weekend = getattr(config, 'ENABLE_WEEKEND_ADAPTIVE_TARGETS', False) and (dt_now.weekday() >= 5)

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
            # 2. TIME-STAGNATION EXIT (Flat/Dead after 240 mins)
            # ----------------------------------------------------
            if trade_duration_mins >= config.MAX_HOLD_MINUTES and not pos.get("tp1_hit"):
                # ONLY exit if trade is DEAD FLAT or NEGATIVE (<= +0.3%). If in profit (> +0.3%), NEVER kill it!
                if gain_pct <= 0.003:
                    closed = self.client.close_paper_position(symbol, current_price, f"Time Stagnation ({trade_duration_mins:.0f}m)")
                    pnl_val = closed.get('realized_pnl_inr', closed.get('realized_pnl', 0.0))
                    bal_val = self.client.portfolio.get('virtual_balance', config.VIRTUAL_INITIAL_BALANCE)
                    msg = (
                        f"⏱️ *{tag} STAGNATION EXIT [{side}]: {symbol}*\n"
                        f"• Time (IST): *{get_now_ist_str()}*\n"
                        f"• Reason: Trade dead flat/negative after {trade_duration_mins:.0f}m ({gain_pct*100:+.2f}%)\n"
                        f"• Realized PnL: *{'+' if pnl_val >= 0 else ''}{sym_curr}{pnl_val:,.2f}*\n"
                        f"• Capital freed for fresh Golden Pocket setups!"
                    )
                    send_telegram_alert(msg)
                    continue

            # ----------------------------------------------------
            # 3. TIER-1 QUICK BREAKEVEN (+1.2% Gain): 100% Risk Free!
            # ----------------------------------------------------
            # Quick Breakeven: Only active if enabled or if already approaching target
            if getattr(config, "ENABLE_PREMATURE_BE", False):
                be_trigger = getattr(config, "WEEKEND_MICRO_BE_TRIGGER_PCT", 0.008) if is_weekend else config.MICRO_BE_TRIGGER_PCT
                if not pos.get("micro_be_hit") and gain_pct >= be_trigger:
                    pos["micro_be_hit"] = True
                    be_buf = config.MICRO_BE_BUFFER_PCT
                    if side == "LONG":
                        pos["sl_price"] = entry_price * (1.0 + be_buf)
                    else:
                        pos["sl_price"] = entry_price * (1.0 - be_buf)
                    pos["locked_gain_pct"] = be_buf
                    self.client.update_stop_loss(symbol, pos["sl_price"])

            # ----------------------------------------------------
            # 4. TIER-2 PROFIT HARVEST: TP1 (Dynamic Wall + Adaptive Harvest)
            # ----------------------------------------------------
            pos_intel = None
            if (getattr(config, 'ENABLE_DYNAMIC_TARGET_WALLS', False) or getattr(config, 'ENABLE_ADAPTIVE_HARVEST_RATIO', False)) and hasattr(self.whale_feed, 'get_institutional_intelligence'):
                try:
                    pos_intel = self.whale_feed.get_institutional_intelligence(symbol, current_price)
                except Exception:
                    pos_intel = None

            # Dynamic Target: Uses 15m/5m Trend-Based Fib Extension Target if available!
            fib_tp1 = pos.get("fib_tp1_gain_pct")
            base_tp1 = fib_tp1 if fib_tp1 else (getattr(config, 'WEEKEND_TP1_PCT', 0.012) if is_weekend else config.TP1_PCT)
            effective_tp1_pct = base_tp1
            wall_note = ""
            if getattr(config, 'ENABLE_DYNAMIC_TARGET_WALLS', False) and pos_intel:
                wall_min = 0.010 if is_weekend else 0.014
                wall_max = 0.018 if is_weekend else 0.025
                if side == "LONG":
                    ask_w = pos_intel.get('ask_wall')
                    if ask_w and ask_w.get('price', 0) > entry_price:
                        wall_gain = (ask_w['price'] - entry_price) / entry_price
                        if wall_min <= wall_gain <= wall_max:
                            effective_tp1_pct = max(wall_min - 0.001, wall_gain - 0.0015)
                            wall_note = f" (Front-run ${ask_w['usd']/1e6:.1f}M Wall @ ${ask_w['price']:.4f})"
                else:
                    bid_w = pos_intel.get('bid_wall')
                    if bid_w and 0 < bid_w.get('price', 0) < entry_price:
                        wall_gain = (entry_price - bid_w['price']) / entry_price
                        if wall_min <= wall_gain <= wall_max:
                            effective_tp1_pct = max(wall_min - 0.001, wall_gain - 0.0015)
                            wall_note = f" (Front-run ${bid_w['usd']/1e6:.1f}M Wall @ ${bid_w['price']:.4f})"

            # Adaptive Harvest Ratio (OI Expansion vs Exhaustion + AI Dynamic Bank)
            import ai_advisor
            dyn_tp1 = ai_advisor.get_dynamic_tp1_book_ratio()
            tp1_ratio = dyn_tp1 if dyn_tp1 else (getattr(config, 'WEEKEND_TP1_BOOK_RATIO', 0.50) if is_weekend else config.TP1_BOOK_RATIO)
            harvest_note = "Standard Fib Target"
            if getattr(config, 'ENABLE_ADAPTIVE_HARVEST_RATIO', False) and pos_intel:
                oi_status = pos_intel.get('oi_status', 'NEUTRAL')
                t_ratio = pos_intel.get('taker_ratio', 1.0)
                if oi_status == "EXPANDING" and ((side == "LONG" and t_ratio >= 1.10) or (side == "SHORT" and t_ratio <= 0.90)):
                    tp1_ratio = 0.20 # Book only 20%, let 80% explode as runner
                    harvest_note = "Strong Institutional Inflow (OI Expanding) -> 80% Kept as Runner"
                elif oi_status == "CONTRACTING" or trade_duration_mins >= 45:
                    tp1_ratio = 0.50 # Bank 50% cash defensively
                    harvest_note = "Momentum Exhaustion / Capital Leaving -> 50% Banked Defensively"
                else:
                    tp1_ratio = config.TP1_BOOK_RATIO
                    harvest_note = "Healthy Fib Impulse"

            if not pos.get("tp1_hit") and gain_pct >= effective_tp1_pct:
                pos["tp1_hit"] = True
                pos["tp1_ratio"] = tp1_ratio

                contracts = pos.get("contracts", 0)
                c_close = max(1, int(round(contracts * tp1_ratio)))
                pos["contracts_remaining"] = max(1, contracts - c_close)
                pos["units_remaining"] = pos.get("units_remaining", 1.0) * (1.0 - tp1_ratio)

                pos_size_inr = pos.get("size_inr", getattr(config, 'FIXED_POSITION_SIZE_INR', 5000.0))
                pnl_inr = pos_size_inr * tp1_ratio * gain_pct
                pos["realized_pnl_inr"] = pos.get("realized_pnl_inr", 0.0) + pnl_inr
                self.client.portfolio["virtual_balance"] += pnl_inr
                self.client.portfolio["realized_pnl"] += pnl_inr

                # Lock SL to guaranteed win (+0.8% on weekend, +1.0% on weekday)
                sl_lock_buf = 0.008 if is_weekend else 0.010
                if side == "LONG":
                    pos["sl_price"] = entry_price * (1.0 + sl_lock_buf)
                else:
                    pos["sl_price"] = entry_price * (1.0 - sl_lock_buf)
                pos["locked_gain_pct"] = sl_lock_buf
                self.client.update_stop_loss(symbol, pos["sl_price"])

                bank_pct = int(round(tp1_ratio * 100))
                rem_pct = int(round((1.0 - tp1_ratio) * 100))
                msg = (
                    f"🎯 *{tag} TP1 HIT [{side}]: {symbol} (+{gain_pct*100:.1f}%)*\n"
                    f"• Time (IST): *{get_now_ist_str()}*\n"
                    f"• Strategy: _{harvest_note}_{wall_note}\n"
                    f"• Cash Booked: *+{sym_curr}{pnl_inr:,.2f} ({bank_pct}% Banked)*\n"
                    f"• SL Locked to: *+1.0% Guaranteed Win* (`${pos['sl_price']}`)\n"
                    f"• Remaining {rem_pct}% continues for TP2 (+{config.TP2_PCT*100:.1f}%)!"
                )
                send_telegram_alert(msg)

            # ----------------------------------------------------
            # 5. TIER-3 PROFIT HARVEST: TP2 (+5.5% Gain) -> Book 40% Cash!
            # ----------------------------------------------------
            if pos.get("tp1_hit") and not pos.get("tp2_hit") and gain_pct >= config.TP2_PCT:
                pos["tp2_hit"] = True
                tp2_ratio = config.TP2_BOOK_RATIO
                contracts = pos.get("contracts", 0)
                c_close = max(1, int(round(contracts * tp2_ratio)))
                pos["contracts_remaining"] = max(1, pos.get("contracts_remaining", contracts) - c_close)
                pos["units_remaining"] = max(0.0, pos.get("units_remaining", 0.70) - tp2_ratio)

                pos_size_inr = pos.get("size_inr", getattr(config, 'FIXED_POSITION_SIZE_INR', 5000.0))
                pnl_inr = pos_size_inr * tp2_ratio * gain_pct
                pos["realized_pnl_inr"] = pos.get("realized_pnl_inr", 0.0) + pnl_inr
                self.client.portfolio["virtual_balance"] += pnl_inr
                self.client.portfolio["realized_pnl"] += pnl_inr

                # Lock SL to +3.0% guaranteed win
                if side == "LONG":
                    pos["sl_price"] = entry_price * 1.025
                else:
                    pos["sl_price"] = entry_price * (1.0 - 0.025)
                pos["locked_gain_pct"] = 0.025
                self.client.update_stop_loss(symbol, pos["sl_price"])

                bank_pct = int(round(tp2_ratio * 100))
                runner_pct = int(round(pos["units_remaining"] * 100))
                msg = (
                    f"🚀 *{tag} TP2 FIB 1.618 EXTENSION HIT [{side}]: {symbol} (+{gain_pct*100:.1f}%)*\n"
                    f"• Time (IST): *{get_now_ist_str()}*\n"
                    f"• Cash Booked: *+{sym_curr}{pnl_inr:,.2f} ({bank_pct}% Banked)*\n"
                    f"• SL Locked to: *+2.5% Super Lock* (`${pos['sl_price']}`)\n"
                    f"• Remaining {runner_pct}% RUNNER running for TP3 (+{config.TP3_PCT*100:.1f}%+)!"
                )
                send_telegram_alert(msg)

            # ----------------------------------------------------
            # 6. TIER-4 RUNNER TRAILING (Wide trailing for 30% runner)
            # ----------------------------------------------------
            if pos.get("tp2_hit"):
                trail_sl_dist = 0.018 # Wide 1.8% breathing room
                if gain_pct > (pos.get("locked_gain_pct", 0.030) + 0.005):
                    new_lock = gain_pct - trail_sl_dist
                    if new_lock > pos.get("locked_gain_pct", 0.030):
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
                    f"🔥 *{tag} TP3 MEGA BLAST JACKPOT [{side}]: {symbol} (+{gain_pct*100:.1f}%)*\n"
                    f"• Time (IST): *{get_now_ist_str()}*\n"
                    f"• Exit Price: `${current_price}`\n"
                    f"• Final Trade PnL: *+{sym_curr}{pnl_val:,.2f}*\n"
                    f"• Account Balance: *{sym_curr}{bal_val:,.2f}*"
                )
                send_telegram_alert(msg)
                continue
