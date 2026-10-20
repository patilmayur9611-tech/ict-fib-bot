"""
========================================================================================
ICT ASIAN JUDAS SWING & OTE MASTER STRATEGY ENGINE (DELTA EXCHANGE INDIA)
Features:
- Asian Session Range Tracker (05:30 AM to 12:30 PM IST)
- London (12:30 - 16:30 IST) & NY (17:30 - 22:30 IST) Killzones
- Judas Swing Liquidity Sweep Detection + Displacement
- 0.618 - 0.705 Fibonacci OTE Retracement Entry
- Protected ATR Buffer Stop Loss
- Rescued Risk Management: 30% TP at +1.0R / Asian Mid + Breakeven SL Lock
========================================================================================
"""
import numpy as np
import datetime
import time
import config

class StrategyEngine:
    def __init__(self, client):
        self.client = client
        self.asian_sessions = {}  # symbol -> {'date', 'high', 'low', 'mid', 'range'}
        self.pending_ote = {}     # symbol -> pending OTE setup

    def is_in_active_killzone(self):
        """Checks if current time is inside London or NY Killzones strictly in IST (+5:30)."""
        now_ist = config.get_now_ist()
        t_minutes = now_ist.hour * 60 + now_ist.minute
        in_london = (config.LONDON_KZ_START_MINUTES <= t_minutes <= config.LONDON_KZ_END_MINUTES)
        in_ny = (config.NY_KZ_START_MINUTES <= t_minutes <= config.NY_KZ_END_MINUTES)
        return in_london or in_ny

    def get_1h_trend_bias(self, symbol):
        """
        Determines 1H Macro Trend Bias using 20-EMA on 1-hour candles.
        """
        candles_1h = self.client.fetch_candles(symbol, resolution=config.TREND_RESOLUTION, limit=50)
        if len(candles_1h) < 10:
            return "NEUTRAL"

        closes = np.array([c["close"] for c in candles_1h])
        ema_period = min(len(closes), 20)
        weights = np.exp(np.linspace(-1., 0., ema_period))
        weights /= weights.sum()
        ema_val = np.convolve(closes, weights, mode='valid')[-1]

        last_close = closes[-1]
        if last_close > ema_val:
            return "BULLISH"
        elif last_close < ema_val:
            return "BEARISH"
        return "NEUTRAL"

    def compute_asian_range(self, symbol, candles):
        """
        Computes Asian Session High, Low, and Mid strictly between 05:30 AM and 12:30 PM IST.
        """
        now_ist = config.get_now_ist()
        today_str = now_ist.strftime('%Y-%m-%d')

        asian_candles = []
        for c in candles:
            # c["time"] is unix timestamp in seconds
            dt = datetime.datetime.fromtimestamp(c["time"], tz=config.IST)
            if dt.strftime('%Y-%m-%d') == today_str:
                t_min = dt.hour * 60 + dt.minute
                if config.ASIAN_START_MINUTES <= t_min <= config.ASIAN_END_MINUTES:
                    asian_candles.append(c)

        if len(asian_candles) < 4:
            return None

        asian_high = max(c["high"] for c in asian_candles)
        asian_low = min(c["low"] for c in asian_candles)
        asian_mid = (asian_high + asian_low) / 2.0
        range_size = asian_high - asian_low

        asian_data = {
            "date": today_str,
            "high": asian_high,
            "low": asian_low,
            "mid": asian_mid,
            "range": range_size
        }
        self.asian_sessions[symbol] = asian_data
        return asian_data

    def calculate_atr(self, candles, period=14):
        """Calculates Average True Range (ATR) across recent candles."""
        if len(candles) < period + 1:
            return 0.0

        trs = []
        for i in range(1, len(candles)):
            c = candles[i]
            prev = candles[i - 1]
            tr = max(c["high"] - c["low"], abs(c["high"] - prev["close"]), abs(c["low"] - prev["close"]))
            trs.append(tr)

        return float(np.mean(trs[-period:]))

    def analyze_symbol(self, symbol, candles):
        """
        Scans candles for ICT Judas Swing and Optimal Trade Entry (OTE) Setups:
        1. Confirms current time is in London or NY Killzone (IST).
        2. Retrieves Asian Session High/Low.
        3. Identifies Judas Swing: Liquidity Sweep of Asian High or Low.
        4. Verifies Institutional Displacement Candle back inside Asian range.
        5. Computes 0.618 - 0.705 Fibonacci OTE retracement levels.
        """
        if not self.is_in_active_killzone():
            return None

        asian = self.compute_asian_range(symbol, candles)
        if not asian or asian["range"] <= 0:
            return None

        atr = self.calculate_atr(candles, period=14)
        if atr <= 0:
            return None

        curr_candle = candles[-1]
        prev_candle = candles[-2]
        trend_bias = self.get_1h_trend_bias(symbol)

        asian_high = asian["high"]
        asian_low = asian["low"]
        asian_mid = asian["mid"]

        # -------------------------------------------------------------
        # SETUP 1: BEARISH JUDAS SWING & SHORT OTE
        # Sweep Asian High (Judas Fakeout) -> Displace Lower -> Sell at 0.618 OTE
        # -------------------------------------------------------------
        if trend_bias in ["BEARISH", "NEUTRAL"]:
            # Check if any recent candle swept Asian High
            recent_candles = candles[-6:]
            swept_high = max(c["high"] for c in recent_candles)
            sweep_depth = swept_high - asian_high

            if sweep_depth >= (config.MIN_SWEEP_DEPTH_ATR * atr):
                # Check for displacement lower (close below Asian High)
                displacement = (curr_candle["open"] - curr_candle["close"])
                if displacement >= (config.MIN_DISPLACEMENT_BODY_ATR * atr) and curr_candle["close"] < asian_high:
                    swing_high = swept_high
                    swing_low = min(curr_candle["low"], prev_candle["low"])
                    swing_range = swing_high - swing_low

                    if swing_range > 0:
                        ote_entry = swing_low + (swing_range * config.OTE_FIB_ENTRY)
                        sl_price = swing_high + (config.SL_ATR_BUFFER * atr)
                        sl_dist = sl_price - ote_entry

                        if sl_dist > 0:
                            # Targets
                            rescue_tp = ote_entry - (config.RESCUE_PROFIT_R * sl_dist) # +1.0R
                            tp1_price = asian_low # Asian Low Target (~1.8R - 2.0R)
                            tp2_price = ote_entry - (config.TP2_R * sl_dist) # 3.0R Runner

                            return {
                                "symbol": symbol,
                                "side": "SHORT",
                                "entry_price": ote_entry,
                                "sl_price": sl_price,
                                "rescue_tp": rescue_tp,
                                "tp1_price": tp1_price,
                                "tp2_price": tp2_price,
                                "asian_high": asian_high,
                                "asian_low": asian_low,
                                "asian_mid": asian_mid,
                                "atr": atr,
                                "setup_type": "ICT_BEARISH_JUDAS_OTE"
                            }

        # -------------------------------------------------------------
        # SETUP 2: BULLISH JUDAS SWING & LONG OTE
        # Sweep Asian Low (Judas Fakeout) -> Displace Higher -> Buy at 0.618 OTE
        # -------------------------------------------------------------
        if trend_bias in ["BULLISH", "NEUTRAL"]:
            # Check if any recent candle swept Asian Low
            recent_candles = candles[-6:]
            swept_low = min(c["low"] for c in recent_candles)
            sweep_depth = asian_low - swept_low

            if sweep_depth >= (config.MIN_SWEEP_DEPTH_ATR * atr):
                # Check for displacement higher (close above Asian Low)
                displacement = (curr_candle["close"] - curr_candle["open"])
                if displacement >= (config.MIN_DISPLACEMENT_BODY_ATR * atr) and curr_candle["close"] > asian_low:
                    swing_low = swept_low
                    swing_high = max(curr_candle["high"], prev_candle["high"])
                    swing_range = swing_high - swing_low

                    if swing_range > 0:
                        ote_entry = swing_high - (swing_range * config.OTE_FIB_ENTRY)
                        sl_price = swing_low - (config.SL_ATR_BUFFER * atr)
                        sl_dist = ote_entry - sl_price

                        if sl_dist > 0:
                            # Targets
                            rescue_tp = ote_entry + (config.RESCUE_PROFIT_R * sl_dist) # +1.0R
                            tp1_price = asian_high # Asian High Target (~1.8R - 2.0R)
                            tp2_price = ote_entry + (config.TP2_R * sl_dist) # 3.0R Runner

                            return {
                                "symbol": symbol,
                                "side": "LONG",
                                "entry_price": ote_entry,
                                "sl_price": sl_price,
                                "rescue_tp": rescue_tp,
                                "tp1_price": tp1_price,
                                "tp2_price": tp2_price,
                                "asian_high": asian_high,
                                "asian_low": asian_low,
                                "asian_mid": asian_mid,
                                "atr": atr,
                                "setup_type": "ICT_BULLISH_JUDAS_OTE"
                            }

        return None
