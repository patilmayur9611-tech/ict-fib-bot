import urllib.request
import json
import time

BINANCE_FUTURES_URL = "https://fapi.binance.com"
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"

def get_binance_symbol(delta_symbol):
    SPECIAL = {
        '1000PEPEUSD': '1000PEPEUSDT',
        '1000BONKUSD': '1000BONKUSDT',
        'BRUSD': 'BRETTUSDT',
        'BASEDUSD': 'BASEDUSDT',
        'NEIROUSD': 'NEIROUSDT'
    }
    if delta_symbol in SPECIAL:
        return SPECIAL[delta_symbol]
    clean = delta_symbol.replace('1000', '')
    if clean.endswith('USD'):
        return clean[:-3] + 'USDT'
    return clean + 'T'

class WhaleFeed:
    def __init__(self):
        self.cached_binance_volumes = {}
        self.cached_intel = {}          # Cache for 4-pillar institutional data (TTL: 15s)
        self.last_intel_fetch = {}
        self.cached_btc_safety = (True, "BTC Initializing")
        self.last_btc_check = 0

    def check_btc_safety(self):
        """
        BTC Safety Shield:
        Checks 15m Bitcoin klines.
        Halts all Altcoin Longs if:
        1. Current or previous 15m kline dropped > 0.70%
        2. BTC dropped > 0.80% in the last 1 hour
        """
        now = time.time()
        if now - self.last_btc_check < 60:
            return self.cached_btc_safety

        try:
            url = f"{BINANCE_FUTURES_URL}/fapi/v1/klines?symbol=BTCUSDT&interval=15m&limit=8"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as r:
                klines = json.loads(r.read().decode('utf-8'))
                if len(klines) >= 4:
                    curr = klines[-1]
                    prev = klines[-2]
                    curr_chg = (float(curr[4]) - float(curr[1])) / float(curr[1])
                    prev_chg = (float(prev[4]) - float(prev[1])) / float(prev[1])
                    if curr_chg < -0.0070 or prev_chg < -0.0070:
                        return False, f"BTC 15m Flash Dump Detected ({min(curr_chg, prev_chg)*100:.2f}%) 🛑"
                    
                    past_4_open = float(klines[-4][1])
                    cur_close = float(curr[4])
                    cum_1h = (cur_close - past_4_open) / past_4_open
                    if cum_1h < -0.0080:
                        return False, f"BTC 1h Dump Detected ({cum_1h*100:.2f}%) 🛑"
            res = (True, "BTC Stable/Bullish ✅")
            self.cached_btc_safety = res
            self.last_btc_check = now
            return res
        except Exception:
            self.last_btc_check = now
            return self.cached_btc_safety

    def get_binance_volume_surge(self, delta_symbol):
        """
        Checks if the leader exchange (Binance) is experiencing an abnormal volume explosion (>2.0x).
        """
        binance_symbol = get_binance_symbol(delta_symbol)

        try:
            url = f"{BINANCE_FUTURES_URL}/fapi/v1/klines?symbol={binance_symbol}&interval=15m&limit=21"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as r:
                klines = json.loads(r.read().decode('utf-8'))
                if len(klines) < 20:
                    return 1.0, 0.0, 0.0
                
                volumes = [float(k[5]) for k in klines[:-1]]
                current_vol = float(klines[-1][5])
                avg_vol = sum(volumes) / len(volumes) if volumes else 1.0
                ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
                
                open_p = float(klines[-1][1])
                close_p = float(klines[-1][4])
                candle_gain_pct = (close_p - open_p) / open_p
                
                return ratio, candle_gain_pct, current_vol
        except Exception:
            return 1.0, 0.0, 0.0

    def get_whale_profile(self, delta_symbol):
        """
        Synthesizes On-chain Whale Inflow, 24h Turnover, and Leader Volume Surge.
        """
        surge_ratio, binance_gain, raw_vol = self.get_binance_volume_surge(delta_symbol)
        
        whale_score = 0
        reasons = []
        
        if surge_ratio >= 3.0:
            whale_score += 40
            reasons.append(f"Leader Binance Volume Blast: {surge_ratio:.1f}x")
        elif surge_ratio >= 2.0:
            whale_score += 25
            reasons.append(f"Leader Binance Volume Surge: {surge_ratio:.1f}x")
            
        if binance_gain >= 0.02:
            whale_score += 30
            reasons.append(f"Strong Leader Expansion (+{binance_gain*100:.1f}%)")
        elif binance_gain >= 0.01:
            whale_score += 15
            reasons.append(f"Positive Leader Momentum (+{binance_gain*100:.1f}%)")
            
        return {
            "symbol": delta_symbol,
            "surge_ratio": surge_ratio,
            "binance_gain": binance_gain,
            "whale_score": whale_score,
            "reasons": reasons
        }

    # ==============================================================================
    # 🌐 4-PILLAR INSTITUTIONAL INTELLIGENCE FEEDS (FREE BINANCE FUTURES API)
    # ==============================================================================

    def get_orderbook_liquidity_walls(self, binance_symbol, current_price):
        """
        Pillar 1: Orderbook Depth & Liquidity Walls (L2 Depth)
        Scans top 100 bids and asks to locate massive limit buy/sell clusters.
        """
        try:
            url = f"{BINANCE_FUTURES_URL}/fapi/v1/depth?symbol={binance_symbol}&limit=100"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as r:
                d = json.loads(r.read().decode('utf-8'))
                
            bids = [[float(p), float(q), float(p)*float(q)] for p, q in d.get('bids', [])]
            asks = [[float(p), float(q), float(p)*float(q)] for p, q in d.get('asks', [])]
            
            # Find nearest significant Bid Wall (Support) between 0.2% and 4.0% below
            bids_in_range = [b for b in bids if current_price > 0 and 0.002 <= (current_price - b[0])/current_price <= 0.040]
            bid_wall = None
            if bids_in_range:
                bids_in_range.sort(key=lambda x: x[2], reverse=True)
                top_b = bids_in_range[0]
                bid_wall = {
                    'price': top_b[0],
                    'usd': top_b[2],
                    'dist_pct': (current_price - top_b[0]) / current_price
                }
                
            # Find nearest significant Ask Wall (Resistance) between 0.2% and 6.0% above
            asks_in_range = [a for a in asks if current_price > 0 and 0.002 <= (a[0] - current_price)/current_price <= 0.060]
            ask_wall = None
            if asks_in_range:
                asks_in_range.sort(key=lambda x: x[2], reverse=True)
                top_a = asks_in_range[0]
                ask_wall = {
                    'price': top_a[0],
                    'usd': top_a[2],
                    'dist_pct': (top_a[0] - current_price) / current_price
                }
                
            return bid_wall, ask_wall
        except Exception:
            return None, None

    def get_taker_flow_ratio(self, binance_symbol):
        """
        Pillar 2: Taker Buy/Sell Volume Ratio (Real-time Market Aggression / CVD)
        Ratio > 1.0 means aggressive market buyers dominate. Ratio < 1.0 means aggressive sellers.
        """
        try:
            url = f"{BINANCE_FUTURES_URL}/futures/data/takerlongshortRatio?symbol={binance_symbol}&period=5m&limit=3"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as r:
                d = json.loads(r.read().decode('utf-8'))
                if d and isinstance(d, list):
                    ratio = float(d[-1].get('buySellRatio', 1.0))
                    buy_vol = float(d[-1].get('buyVol', 0))
                    sell_vol = float(d[-1].get('sellVol', 0))
                    return ratio, buy_vol, sell_vol
            return 1.0, 0.0, 0.0
        except Exception:
            return 1.0, 0.0, 0.0

    def get_open_interest_trend(self, binance_symbol):
        """
        Pillar 3: Real-Time Open Interest (OI) Trend (15m Flow)
        Expanding OI = New institutional capital flowing in (Real move).
        Contracting OI = Capital leaving (Short squeeze / Fakeout trap).
        """
        try:
            url = f"{BINANCE_FUTURES_URL}/futures/data/openInterestHist?symbol={binance_symbol}&period=5m&limit=4"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as r:
                d = json.loads(r.read().decode('utf-8'))
                if len(d) >= 2:
                    cur_oi = float(d[-1].get('sumOpenInterestValue', 0))
                    past_oi = float(d[0].get('sumOpenInterestValue', 0))
                    if past_oi > 0:
                        oi_chg = (cur_oi - past_oi) / past_oi
                        status = "EXPANDING" if oi_chg >= 0.010 else ("CONTRACTING" if oi_chg <= -0.010 else "NEUTRAL")
                        return oi_chg, cur_oi, status
            return 0.0, 0.0, "NEUTRAL"
        except Exception:
            return 0.0, 0.0, "NEUTRAL"

    def get_top_traders_sentiment(self, binance_symbol):
        """
        Pillar 4: Top Trader Accounts Long/Short Ratio (Smart Money Consensus)
        Tracks the top 20% most profitable accounts on Binance.
        """
        try:
            url = f"{BINANCE_FUTURES_URL}/futures/data/topLongShortPositionRatio?symbol={binance_symbol}&period=5m&limit=3"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as r:
                d = json.loads(r.read().decode('utf-8'))
                if d and isinstance(d, list):
                    long_acc = float(d[-1].get('longAccount', 0.50))
                    short_acc = float(d[-1].get('shortAccount', 0.50))
                    ls_ratio = float(d[-1].get('longShortRatio', 1.0))
                    return long_acc, short_acc, ls_ratio
            return 0.50, 0.50, 1.0
        except Exception:
            return 0.50, 0.50, 1.0

    def get_funding_rate_and_squeeze(self, binance_symbol):
        """
        Pillar 5: Predicted Funding Rate & Short-Squeeze Detector
        Scans real-time funding rate and Spot-Perp premium.
        - Negative Funding (<= -0.015%): Trapped shorts paying longs -> Explosive Short-Squeeze UP
        - Extreme Positive Funding (>= +0.050%): Overleveraged longs paying shorts -> Long Flush Trap
        """
        try:
            url = f"{BINANCE_FUTURES_URL}/fapi/v1/premiumIndex?symbol={binance_symbol}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as r:
                d = json.loads(r.read().decode('utf-8'))
                funding_rate = float(d.get('lastFundingRate', 0.0))
                mark_price = float(d.get('markPrice', 0.0))
                index_price = float(d.get('indexPrice', 0.0))
                premium_pct = ((mark_price - index_price) / index_price) * 100.0 if index_price > 0 else 0.0

                if funding_rate <= -0.00015:
                    squeeze_bias = "SHORT_SQUEEZE"
                elif funding_rate >= 0.00050:
                    squeeze_bias = "LONG_FLUSH"
                else:
                    squeeze_bias = "NEUTRAL"

                return funding_rate, premium_pct, squeeze_bias
        except Exception:
            return 0.0, 0.0, "NEUTRAL"

    def get_institutional_intelligence(self, delta_symbol, current_price):
        """
        Unified 5-Pillar Institutional Confluence Engine.
        Caches for 15 seconds to prevent rate limits and ensure lightning-fast execution.
        """
        now = time.time()
        last_fetch = self.last_intel_fetch.get(delta_symbol, 0)
        if (now - last_fetch) < 15 and delta_symbol in self.cached_intel:
            return self.cached_intel[delta_symbol]

        binance_symbol = get_binance_symbol(delta_symbol)

        # 1. Depth Walls
        bid_wall, ask_wall = self.get_orderbook_liquidity_walls(binance_symbol, current_price)
        # 2. Taker Flow Ratio
        taker_ratio, buy_vol, sell_vol = self.get_taker_flow_ratio(binance_symbol)
        # 3. Open Interest Momentum
        oi_chg, oi_usd, oi_status = self.get_open_interest_trend(binance_symbol)
        # 4. Top Trader Sentiment
        top_long_pct, top_short_pct, ls_ratio = self.get_top_traders_sentiment(binance_symbol)
        # 5. Funding Rate & Squeeze Detector
        funding_rate, premium_pct, squeeze_bias = self.get_funding_rate_and_squeeze(binance_symbol)

        intel = {
            "symbol": delta_symbol,
            "binance_symbol": binance_symbol,
            "bid_wall": bid_wall,
            "ask_wall": ask_wall,
            "taker_ratio": taker_ratio,
            "buy_vol": buy_vol,
            "sell_vol": sell_vol,
            "oi_change_15m_pct": oi_chg,
            "oi_status": oi_status,
            "top_long_pct": top_long_pct,
            "top_short_pct": top_short_pct,
            "ls_ratio": ls_ratio,
            "funding_rate": funding_rate,
            "premium_pct": premium_pct,
            "squeeze_bias": squeeze_bias,
            "timestamp": now
        }

        self.cached_intel[delta_symbol] = intel
        self.last_intel_fetch[delta_symbol] = now
        return intel
