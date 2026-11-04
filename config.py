"""
========================================================================================
ICT ASIAN JUDAS SWING & OTE MASTER BOT - CONFIGURATION (INR EDITION)
Exchange: Delta Exchange India (api.india.delta.exchange)
Currency: Indian Rupee (INR - ₹)
Clock: Strictly Locked to Indian Standard Time (IST, UTC+5:30)
========================================================================================
"""
import os
import datetime

# ========================================================================================
# 1. EXPLICIT INDIAN STANDARD TIME (IST) TIMEZONE LOCK (UTC+5:30)
# Guarantees identical clock on Local Windows, Cloud VPS, Docker, and Render (which defaults to UTC)
# ========================================================================================
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def get_now_ist():
    """Returns current datetime strictly locked to Indian Standard Time (IST, UTC+5:30)."""
    return datetime.datetime.now(IST)

def format_timestamp_ist(ts):
    """Converts a unix timestamp (seconds) into formatted IST string."""
    return datetime.datetime.fromtimestamp(ts, tz=IST).strftime('%Y-%m-%d %H:%M:%S')

# ========================================================================================
# 2. TRADING MODE
# True  = Simulated execution with realistic fills and slippage (100% safe paper trading)
# False = Real order execution on Delta Exchange India via authenticated REST API
# ========================================================================================
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

# ========================================================================================
# 3. TELEGRAM BOT ALERTS & REMOTE CONTROL (AUTHENTICATED)
# ========================================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8792852123:AAENvIX0o_4ETvLsT-Xy3wj-Gq-fokMxhF8")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7271911207")

# ========================================================================================
# 4. DELTA EXCHANGE INDIA API CREDENTIALS (Required if PAPER_TRADING = False)
# ========================================================================================
DELTA_API_KEY = os.getenv("DELTA_INDIA_API_KEY", "YOUR_DELTA_INDIA_API_KEY")
DELTA_API_SECRET = os.getenv("DELTA_INDIA_API_SECRET", "YOUR_DELTA_INDIA_API_SECRET")
DELTA_BASE_URL = "https://api.india.delta.exchange"
DELTA_WS_URL = "wss://socket.india.delta.exchange"

# ========================================================================================
# 5. INDIAN RUPEE (INR - ₹) CAPITAL MANAGEMENT & 20X LEVERAGE
# Delta Exchange India runs deposits, withdrawals, margin, and balances in INR (₹)
# ========================================================================================
USD_INR_RATE = float(os.getenv("USD_INR_RATE", "90.0"))        # Conversion peg (~₹90 / USD)
INITIAL_CAPITAL_INR = float(os.getenv("INITIAL_CAPITAL_INR", "2000.0"))    # ₹2,000 Starting Capital
MAX_ACTIVE_CAPITAL_INR = float(os.getenv("MAX_ACTIVE_CAPITAL_INR", "100000.0")) # ₹1,00,000 Active Risk Ceiling (Cap)
RISK_PER_TRADE_PCT = 0.025        # 2.5% risk per trade (e.g. ₹50 risk on ₹2,000 capital)
LEVERAGE = 20                    # 20x Leverage (Isolated Margin)
MAX_CONCURRENT_TRADES = 3        # Maximum simultaneous open trades
TARGET_POSITION_INR = float(os.getenv("TARGET_POSITION_INR", "15000.0")) # Target ₹15,000 Position Size (~₹750 margin at 20x)
MIN_POSITION_INR = 12000.0                                               # ₹12,000 Minimum Floor
MAX_POSITION_INR = 16000.0                                               # ₹16,000 STRICT Maximum Hard Cap (Non-Compounding)

def format_inr(amount):
    """Formats currency into Indian Rupee format."""
    return f"₹{amount:,.2f}"

# ========================================================================================
# 6. ASSET UNIVERSE: DYNAMIC INSTITUTIONAL SCREENER (240+ COIN AUTO-FILTER)
# Delta Exchange India Bulk Public Endpoint Filter Engine
# ========================================================================================
DYNAMIC_UNIVERSE_ENABLED = True
DYNAMIC_UNIVERSE_LIMIT = 25                # Top 25 high-liquidity coins
DYNAMIC_MIN_VOLUME_USD = 500000.0          # $500,000 (~₹4.5 Crore) minimum 24h volume
DYNAMIC_MAX_SPREAD_PCT = 0.0020            # 0.20% maximum bid-ask spread
DYNAMIC_REFRESH_INTERVAL_SECONDS = 3600    # Refresh top universe every 1 hour (3600s)

# Core staples always included in active universe (High-volatility, explosive altcoins)
CORE_STAPLES = [
    'SOLUSD',    # Solana (High Volatility)
    'DOGEUSD',   # Dogecoin (High Volatility)
    'XRPUSD',    # Ripple (High Volatility)
    'ADAUSD',    # Cardano (High Volatility)
    'AVAXUSD',   # Avalanche (High Volatility)
    'LINKUSD',   # Chainlink (High Volatility)
    'UNIUSD',    # Uniswap (High Volatility)
    'RUNEUSD'    # Thorchain (Very High Volatility - 2.5x Move)
]

# Excluded Non-Crypto / Low-Volatility Assets (Gold, Silver, Oil, Stock tokens)
EXCLUDED_KEYWORDS = [
    'PAXG', 'XAUT', 'GOLD', 'SILVER', 'SLV', 'OIL', 'US500', 'SPX', 'QQQ', 'AAPL', 'TSLA', 'NVDA', 'MSFT', 'AMZN'
]

# Fallback default universe if offline
SYMBOLS = list(CORE_STAPLES)

# DELTA EXCHANGE INDIA CONTRACT VALUES (Units per 1 Contract Lot) - Fallback Defaults
CONTRACT_VALUES = {
    'SOLUSD': 1.0,      # 1 Contract = 1 SOL
    'DOGEUSD': 100.0,   # 1 Contract = 100 DOGE
    'BTCUSD': 0.001,    # 1 Contract = 0.001 BTC
    'ETHUSD': 0.01,     # 1 Contract = 0.01 ETH
    'ADAUSD': 1.0,      # 1 Contract = 1 ADA
    'AVAXUSD': 1.0,     # 1 Contract = 1 AVAX
    'BNBUSD': 0.1       # 1 Contract = 0.1 BNB
}

# ========================================================================================
# 7. ICT SESSIONS & TIMEFRAMES (LOCKED STRICTLY TO IST UTC+5:30)
# ========================================================================================
CANDLE_RESOLUTION = "15m"        # 15-Minute Entry Candles
TREND_RESOLUTION = "1h"          # 1-Hour Trend Bias

# Asian Session: 05:30 AM to 12:30 PM IST
ASIAN_START_MINUTES = 5 * 60 + 30   # 330 mins (05:30 IST)
ASIAN_END_MINUTES = 12 * 60 + 30    # 750 mins (12:30 IST)

# London Killzone: 12:30 PM to 04:30 PM IST (Judas Sweep Execution)
LONDON_KZ_START_MINUTES = 12 * 60 + 30  # 750 mins (12:30 IST)
LONDON_KZ_END_MINUTES = 16 * 60 + 30    # 990 mins (16:30 IST)

# NY Killzone: 05:30 PM to 10:30 PM IST (Displacement & Expansion)
NY_KZ_START_MINUTES = 17 * 60 + 30      # 1050 mins (17:30 IST)
NY_KZ_END_MINUTES = 22 * 60 + 30        # 1350 mins (22:30 IST)

# 24X7 NONSTOP TRADING MODE (CRYPTO EDITION):
# True  = Trades 24x7 across London, NY, and Night Expansion (12:30 PM to 05:30 AM next day).
#         05:30 AM to 12:30 PM is dedicated to Asian Range building.
# False = Strictly limits entry to London & NY Killzones.
ENABLE_24X7_TRADING = True
SKIP_WEEKENDS = False  # Crypto markets operate 24/7/365

# ========================================================================================
# 8. ICT OTE & DISPLACEMENT RULES
# ========================================================================================
MIN_DISPLACEMENT_BODY_ATR = 0.70 # Minimum 0.70 ATR displacement candle
MIN_SWEEP_DEPTH_ATR = 0.40       # Minimum 0.40 ATR sweep depth beyond Asian boundary
OTE_FIB_ENTRY = 0.618            # 0.618 Fibonacci OTE entry
OTE_FIB_DEEP = 0.705             # 0.705 Fibonacci sweet spot
SL_ATR_BUFFER = 0.25             # 0.25 ATR protective buffer beyond sweep wick tip

# ========================================================================================
# 9. RESCUED RISK MANAGEMENT RULES (Converts 50% losses into green trades!)
# ========================================================================================
# Level 1: +1.0R / Asian Mid -> Book 60% profit immediately & move SL to BREAKEVEN PLUS (slightly above entry)
RESCUE_PROFIT_R = 1.0
RESCUE_CLOSE_RATIO = 0.60
BREAKEVEN_PLUS_R = 0.40         # +0.40R Guaranteed Solid Profit on reversal exit (no more ₹4!)

# Level 2: Asian Opposite High/Low (1.8R - 2.0R) -> Book 25% profit
TP1_R = 1.9
TP1_CLOSE_RATIO = 0.25

# Level 3: Runner (Remaining 15%) -> Trail to 3.0R
TP2_R = 3.0
RUNNER_RATIO = 0.15

# ========================================================================================
# 10. CLOUD KEEPALIVE & HEALTHCHECK SERVER (RENDER DEPLOYMENT)
# Render dynamically passes $PORT environment variable (defaults to 10000)
# ========================================================================================
SERVER_HOST = "0.0.0.0"
SERVER_PORT = int(os.getenv("PORT", "10000"))
