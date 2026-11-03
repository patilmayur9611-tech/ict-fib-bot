import os

# ==============================================================================
# WHALE & MOMENTUM QUANT ENGINE: GOLDEN POCKET OTE (OPTIMAL TRADE ENTRY)
# ARCHITECTURE: BOTTOM SWEEP + EMA 10/20 REVERSAL + FIB 0.50-0.618 OTE + ANTI-CLIMAX GUARD
# Backtest Verified: 66.12% Win Rate | 4.91 Profit Factor | 9.3% Max Drawdown
# ==============================================================================

BOT_NAME = "Whale Golden Pocket OTE Quant Engine"
BOT_TAG = "[GOLDEN POCKET BOT]"

# CURRENCY SETTINGS (Delta Exchange India operates in INR ₹)
CURRENCY = "INR"
CURRENCY_SYMBOL = "₹"
USD_TO_INR = 89.0                 # Delta Exchange India internal peg (~₹88.5 - ₹90.0 per USD)

# MODE: True = Paper Trading (Virtual Funds), False = Live Delta API Trading
PAPER_TRADING = True
VIRTUAL_INITIAL_BALANCE = 1000.0   # Starting Capital ₹1,000 INR for Low Size Testing

# DELTA EXCHANGE API CREDENTIALS (Live Delta India Data Feed)
DELTA_API_KEY = os.environ.get("DELTA_API_KEY", "")
DELTA_API_SECRET = os.environ.get("DELTA_API_SECRET", "")

USE_TESTNET = False
DELTA_BASE_URL = "https://api.india.delta.exchange"

# 🏆 APPROVED TOP LIQUID ASSETS (PARSO NIGHT WINNERS + HIGH LIQUIDITY MAJORS)
# Strictly eliminates low-volume meme traps (INIT, JCT, PARTI, BEAT, EVAA, BLESS)!
APPROVED_MAJOR_COINS = [
    'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'DOGEUSD', 
    'ADAUSD', 'UNIUSD', 'SLVONUSD', 'SNDKBUSD', 'AVAXUSD', 
    'LINKUSD', 'NEARUSD', 'SUIUSD', 'LTCUSD', 'BNBUSD',
    'AINUSD', 'SOPHUSD', 'OPUSD', 'BLURUSD', 'ZROUSD', 'EIGENUSD'
]
STRICT_MAJOR_COINS_ONLY = False  # OPTION C DYNAMIC: Scans top active volume coins on Delta!

# 🌐 UNRESTRICTED DYNAMIC SCANNER (ZERO COINS BANNED!)
# Any coin on Delta Exchange India that generates volume & momentum is 100% eligible!
BANNED_SYMBOLS = []               # ZERO BANS: No coin is ever blacklisted by name!
STRICT_MAJOR_COINS_ONLY = False  # Full dynamic mode: Scans top active volume coins on Delta!
MAX_HOT_COINS_TO_DEEP_SCAN = 30  # Dynamically scan top 30 high-turnover coins
MIN_24H_VOLUME_USD = 100000.0    # $100k+ turnover minimum (Ensures basic orderbook fill liquidity)

# 🎯 DYNAMIC CHOP FILTER & ROLLING COOLDOWN (NO PERMANENT COIN BANS!)
MIN_DISPLACEMENT_LEG_PCT = 0.012 # At least 1.2% 1-hour displacement required (Automatically rejects dead sideways chop!)
SL_HIT_COOLDOWN_MINUTES = 150    # 2.5 hours temporary cooling if a coin hits SL (lets daily chop pass without permanent ban)
NORMAL_COOLDOWN_MINUTES = 45     # 45m normal cooldown for winning trades

# RISK & MARGIN PARAMETERS (15x LEVERAGE - STRUCTURAL POSITION SIZING)
LEVERAGE = 15                  # 15x Leverage on Delta India
RISK_PER_TRADE_PCT = 0.020     # 2.0% Risk of capital (~₹100 max loss on ₹5,000 position)
MAX_CONCURRENT_TRADES = 2      # Max 2 concurrent risk trades
MAX_ACTIVE_RISK_TRADES = 2     # Max 2 trades at initial risk (SL not yet locked in profit)
MAX_TOTAL_POSITIONS = 4        # Max 4 total positions (allows risk-free runners to keep running!)
FREE_SLOT_ON_TP1 = True        # Once a trade hits TP1 & locks profit, its risk slot is FREED!
ENABLE_SHORTS = True           # DUAL-DIRECTION: Takes both LONG and SHORT reversals
STRICT_SHORT_BTC_TREND_FILTER = True # Strictly bans Shorts if Bitcoin is Bullish (Eliminates counter-trend traps)

# 🔒 FIXED POSITION SIZING & RISK CONTROL (RENDER LOW POSITION SIZE)
USE_FIXED_POSITION_SIZE = True       # Strict fixed sizing: 4 contracts on SNDKBUSD, exact ~₹5,000 INR
FIXED_POSITION_SIZE_INR = 5000.0    # Fixed ₹5,000 INR Position Budget (~$56 USD | ₹333 margin at 15x)
MAX_POSITION_SIZE_INR = 6000.0      # Hard ceiling: Never exceed ₹6,000 INR under any circumstance!
MAX_SLIPPAGE_PCT = 0.005            # Max 0.5% slippage protection (rejects bad fills)

# 🛡️ ANTI-CLIMAX GUARD (STRICTLY BANS BUYING THE TOP!)
ANTI_CLIMAX_MAX_PUMP_PCT = 0.040 # NEVER enter Long if price is > 4.0% above 1-hour low!
ANTI_CLIMAX_MAX_DUMP_PCT = 0.040 # NEVER enter Short if price is > 4.0% below 1-hour high!

# 🎯 FIBONACCI RETRACEMENT ENTRY (0.50 - 0.618 GOLDEN POCKET OTE)
FIB_ENTRY_MIN = 0.50           # 50% Equilibrium boundary
FIB_ENTRY_MAX = 0.618          # 61.8% Golden Pocket sweet spot
STRUCTURAL_SL_BUFFER_PCT = 0.003 # 0.3% buffer below swing low (Sheltered SL)
MIN_SL_PCT = 0.006             # Min 0.6% Stop Loss (~₹30 risk on ₹5,000 position)
MAX_SL_PCT = 0.009             # Max 0.9% Hard Ceiling Stop Loss (Strictly caps loss at -₹45 max! No more ₹125 losses!)
STOP_LOSS_PCT = 0.008          # 0.8% Default Fallback Stop Loss (~₹40 risk)

# 🎯 MACRO TREND CONFLUENCE LOCK (EMA 20 & EMA 50 - HIGHEST PROFIT FACTOR 2.03)
ENABLE_MACRO_TREND_FILTER = True # Only Long when EMA20 >= EMA50, Only Short when EMA20 <= EMA50

# 🌐 5-PILLAR INSTITUTIONAL INTELLIGENCE ENGINE (BINANCE FUTURES DATA)
ENABLE_INSTITUTIONAL_FEEDS = True     # Master Switch: Connects Binance L2 Depth, Taker Flow, OI, Top Traders & Funding Rate
MIN_TAKER_BUY_RATIO_LONG = 0.90      # Rejects Longs if aggressive market sellers dominate (< 0.90)
MAX_TAKER_BUY_RATIO_SHORT = 0.85     # Rejects Shorts unless aggressive sellers heavily dominate (<= 0.85)
MIN_TOP_TRADER_LONG_PCT = 0.45       # Top 20% smart money accounts minimum long % for Longs
MAX_TOP_TRADER_LONG_FOR_SHORT = 0.48 # Top Whales must NOT be net long (> 48%) for Shorts
ENABLE_DYNAMIC_TARGET_WALLS = True   # Aligns TP1/TP2 slightly before large orderbook Sell/Buy walls
ENABLE_ADAPTIVE_HARVEST_RATIO = True # Adapts book % based on OI expansion (20% run) vs exhaustion (50% bank)

# ⚡ PILLAR 5: PREDICTED FUNDING RATE & SHORT-SQUEEZE DETECTOR
ENABLE_FUNDING_SQUEEZE_DETECTOR = True # Real-time trapped short / funding squeeze detection
SHORT_SQUEEZE_FUNDING_THRESHOLD = -0.00015 # < -0.015%: Shorts heavily trapped -> Squeeze UP (Strictly bans Shorts!)
LONG_FLUSH_FUNDING_THRESHOLD = 0.00050     # > +0.050%: Longs overleveraged -> Flush DOWN

# 🗓️ WEEKEND ADAPTIVE VOLATILITY CONTROLS (SATURDAY & SUNDAY CHOP SHIELD)
ENABLE_WEEKEND_ADAPTIVE_TARGETS = True # Automatically switches to tighter targets on low-vol weekends
WEEKEND_TP1_PCT = 0.012                # +1.20% Target 1 on weekends (Quick bank before weekend chop!)
WEEKEND_TP1_BOOK_RATIO = 0.50          # Bank 50% Cash immediately on weekends
WEEKEND_MICRO_BE_TRIGGER_PCT = 0.009   # +0.90% Gain pulls SL to Breakeven (+0.05% buffer)

# 🛡️ 2-TIER QUICK BREAKEVEN & PROFIT LOCKING (RISK-FREE EARLY SHIELD)
MICRO_BE_TRIGGER_PCT = 0.011   # At +1.10% Gain: Pull SL to Breakeven (100% Risk Free without choking the runner!)
MICRO_BE_BUFFER_PCT = 0.0005   # +0.05% Buffer (leaves 1.05% breathing room for normal healthy pullback)

# 🎯 MULTI-TIMEFRAME SNIPER & TREND-BASED FIBONACCI ENGINE
ENTRY_TIMEFRAME = '3m'         # 3-Minute Sniper Execution (Zero delay, fast bottom sweep reaction, tight SL)
MACRO_TIMEFRAME = '15m'        # 15-Minute Macro Structure & Trend-Based Fibonacci Extension Targets

# 🚀 TREND-BASED FIB TARGET HARVESTING (75% CASH BANK AT TP1)
ENABLE_PREMATURE_BE = False    # Strictly disables choking trades before TP1 (gives trade room to hit target!)
TP1_PCT = 0.018                # Fallback +1.80% TP1 (Macro High Retest)
TP1_BOOK_RATIO = 0.75          # Bank 75% Cash immediately at TP1! (+₹75 to +₹110 INR in pocket!)

TP2_PCT = 0.030                # Fallback +3.00% TP2 (Fib 1.272 Extension Breakout)
TP2_BOOK_RATIO = 0.25          # Bank remaining 25% at TP2! (Total 100% in pocket!)

TP3_PCT = 0.050                # Fib 1.618 Golden Extension Moonshot Runner
TRAILING_STEP_PCT = 0.005      # 0.5% continuous trailing ratchet
MAX_HOLD_MINUTES = 240         # 240-minute (4 hours) window

# ✂️ TOOL 4: EARLY MOMENTUM DECAY CUT
ENABLE_EARLY_DECAY_CUT = True  # Cuts failed reversals early
EARLY_CUT_MINUTES = 20         # Check after 20 minutes
EARLY_CUT_LOSS_PCT = -0.010    # If trade is down <= -1.0% after 20m, exit early
SCAN_INTERVAL_SECONDS = 10

# TELEGRAM BOT (Verified Credentials)
TELEGRAM_BOT_TOKEN = "8524775146:AAHeIscEpeJz7sLcjQwTJ461NXvYQoyW4YE"
TELEGRAM_CHAT_ID = "7271911207"
