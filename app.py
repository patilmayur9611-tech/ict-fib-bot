#!/usr/bin/env python3
"""
========================================================================================
   ICT ASIAN JUDAS SWING & OTE 24/7 AUTONOMOUS BOT (RENDER + TELEGRAM + LOCKED IST CLOCK)
========================================================================================
- CLOCK: Hardcoded to Indian Standard Time (IST = UTC+5:30).
  Server chahe Render (USA) par ho ya Europe me, bot hamesha 100% accurate India time par chalega!
- Time Mappings in IST:
    * Asian Session:   05:30 AM to 12:30 PM IST (00:00 - 07:00 UTC)
    * London Killzone: 12:30 PM to 04:30 PM IST (07:00 - 11:00 UTC)
    * NY Killzone:     05:30 PM to 10:30 PM IST (12:00 - 17:00 UTC)
- Telegram Notifications & Commands: /status, /balance, /positions, /time
========================================================================================
"""

import os
import sys
import time
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
import requests
import pandas as pd
import numpy as np

try:
    import ccxt
except ImportError:
    ccxt = None

# ========================================================================================
# 1. EXPLICITLY LOCKED INDIAN STANDARD TIME (IST = UTC + 5:30)
# ========================================================================================
IST = timezone(timedelta(hours=5, minutes=30))

def get_now_ist():
    """Hamesha guaranteed India ka time return karega chahe server US me ho ya India me."""
    return datetime.now(IST)

def format_ist_str(dt=None):
    if dt is None:
        dt = get_now_ist()
    return dt.strftime("%Y-%m-%d %I:%M:%S %p IST")

# Configure Logging with IST Timestamp
class ISTFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=IST)
        return dt.strftime(datefmt or "%Y-%m-%d %H:%M:%S IST")

logger = logging.getLogger("Render_ICT_Bot")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ISTFormatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.handlers = [handler]

# ========================================================================================
# 2. CONFIGURATION & ENVIRONMENT VARIABLES
# ========================================================================================
PORT = int(os.environ.get("PORT", 10000))
MODE = os.environ.get("MODE", "PAPER_TRADING")
EXCHANGE_ID = os.environ.get("EXCHANGE", "binance")
API_KEY = os.environ.get("API_KEY", "")
API_SECRET = os.environ.get("API_SECRET", "")
USE_TESTNET = os.environ.get("USE_TESTNET", "true").lower() == "true"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8792852123:AAENvIX0o_4ETvLsT-Xy3wj-Gq-fokMxhF8")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "7271911207")

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT"]
TIMEFRAME = "15m"
INITIAL_CAPITAL = float(os.environ.get("INITIAL_CAPITAL", 2000.0))
MAX_CAPITAL_CAP = float(os.environ.get("MAX_CAPITAL_CAP", 100000.0))
RISK_PCT = 0.02
LEVERAGE = int(os.environ.get("LEVERAGE", 20))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", 60))

# ========================================================================================
# 3. TELEGRAM MESSAGING ENGINE
# ========================================================================================
def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info(f"[TELEGRAM ALERT SIMULATED]:\n{text}")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown"
        }
        resp = requests.post(url, json=payload, timeout=8)
        if resp.status_code != 200:
            logger.error(f"Telegram send failed: {resp.text}")
    except Exception as e:
        logger.error(f"Telegram connection error: {e}")

# ========================================================================================
# 4. HTTP HEALTHCHECK SERVER FOR RENDER.COM
# ========================================================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        health_data = {
            "status": "ONLINE",
            "bot_mode": MODE,
            "clock_timezone": "Indian Standard Time (IST = UTC+5:30)",
            "current_time_ist": format_ist_str(),
            "active_capital": bot_instance.capital if 'bot_instance' in globals() else INITIAL_CAPITAL,
            "open_positions": len(bot_instance.active_positions) if 'bot_instance' in globals() else 0
        }
        self.wfile.write(json.dumps(health_data, indent=2).encode("utf-8"))

    def log_message(self, format, *args):
        return

def run_http_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info(f"🌐 Render Healthcheck Web Server listening on port {PORT}...")
    server.serve_forever()

# ========================================================================================
# 5. ICT 24/7 TRADING ENGINE (LOCKED TO IST)
# ========================================================================================
class ICTBot:
    def __init__(self):
        self.capital = INITIAL_CAPITAL
        self.active_positions = {}
        self.session_data = {}
        self.init_exchange()

    def init_exchange(self):
        if ccxt:
            exch_class = getattr(ccxt, EXCHANGE_ID)
            if MODE == "LIVE_TRADING":
                self.exchange = exch_class({
                    'apiKey': API_KEY,
                    'secret': API_SECRET,
                    'enableRateLimit': True,
                    'options': {'defaultType': 'future'}
                })
                if USE_TESTNET:
                    self.exchange.set_sandbox_mode(True)
                    logger.info("Connected to exchange in TESTNET mode.")
                else:
                    logger.info("Connected to exchange in LIVE PRODUCTION mode.")
            else:
                self.exchange = exch_class({'enableRateLimit': True})
                logger.info("Running in PAPER TRADING simulation mode.")
        else:
            self.exchange = None
            logger.warning("CCXT not available, running in mock mode.")

    def fetch_candles(self, symbol, limit=100):
        try:
            if self.exchange:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=limit)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                # Convert timestamps strictly to IST!
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True).dt.tz_convert(IST)
                df.set_index('datetime', inplace=True)
                return df
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()

    def calculate_indicators(self, df):
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        return df

    def update_asian_session(self, symbol, df):
        # Asian session in IST: 05:30 AM to 12:30 PM IST (00:00 - 07:00 UTC)
        now_ist = get_now_ist()
        today_ist = now_ist.date()
        
        df_today = df[df.index.date == today_ist]
        # Filter candles between 05:30 and 12:30 IST
        asian = df_today[
            ((df_today.index.hour == 5) & (df_today.index.minute >= 30)) |
            ((df_today.index.hour >= 6) & (df_today.index.hour < 12)) |
            ((df_today.index.hour == 12) & (df_today.index.minute <= 30))
        ]
        
        if len(asian) >= 3:
            ah = asian['high'].max()
            al = asian['low'].min()
            self.session_data[symbol] = {
                'high': ah,
                'low': al,
                'mid': (ah + al) / 2.0,
                'range': ah - al,
                'date': today_ist
            }

    def check_signals(self, symbol, df):
        if symbol not in self.session_data:
            return None
            
        s = self.session_data[symbol]
        if s['range'] <= 0:
            return None
            
        now_ist = get_now_ist()
        hour_ist = now_ist.hour
        min_ist = now_ist.minute
        time_minutes = hour_ist * 60 + min_ist
        
        # Killzones in IST:
        # London KZ: 12:30 PM to 04:30 PM IST (750 to 990 minutes)
        # NY KZ:     05:30 PM to 10:30 PM IST (1050 to 1350 minutes)
        in_london_kz = (750 <= time_minutes <= 990)
        in_ny_kz     = (1050 <= time_minutes <= 1350)
        
        if not (in_london_kz or in_ny_kz):
            return None # Outside active killzones
            
        curr_b = df.iloc[-1]
        prev_b = df.iloc[-2]
        atr = curr_b['atr'] if not pd.isna(curr_b['atr']) else (s['range'] * 0.1)
        
        is_bull = curr_b['close'] > curr_b['ema200']
        is_bear = curr_b['close'] < curr_b['ema200']
        
        # BUY SIGNAL: Asian Low Swept + Strong Displacement
        if is_bull and (prev_b['low'] < s['low']) and (curr_b['close'] > s['low']) and (curr_b['close'] > curr_b['open']):
            sw_low = min(prev_b['low'], curr_b['low'])
            sw_high = max(prev_b['high'], curr_b['high'])
            impulse = sw_high - sw_low
            
            entry = sw_high - (0.618 * impulse)
            sl = sw_low - (atr * 0.25)
            risk = entry - sl
            tp1 = s['high']
            
            if risk > 0 and (tp1 - entry) >= risk * 1.0:
                return {
                    'type': 'BUY',
                    'symbol': symbol,
                    'entry': entry,
                    'sl': sl,
                    'risk': risk,
                    'tp_mid': s['mid'],
                    'tp1': tp1,
                    'tp2': sw_high + (0.27 * impulse),
                    'time_ist': format_ist_str()
                }

        # SELL SIGNAL: Asian High Swept + Strong Displacement
        if is_bear and (prev_b['high'] > s['high']) and (curr_b['close'] < s['high']) and (curr_b['close'] < curr_b['open']):
            sw_high = max(prev_b['high'], curr_b['high'])
            sw_low = min(prev_b['low'], curr_b['low'])
            impulse = sw_high - sw_low
            
            entry = sw_low + (0.618 * impulse)
            sl = sw_high + (atr * 0.25)
            risk = sl - entry
            tp1 = s['low']
            
            if risk > 0 and (entry - tp1) >= risk * 1.0:
                return {
                    'type': 'SELL',
                    'symbol': symbol,
                    'entry': entry,
                    'sl': sl,
                    'risk': risk,
                    'tp_mid': s['mid'],
                    'tp1': tp1,
                    'tp2': sw_low - (0.27 * impulse),
                    'time_ist': format_ist_str()
                }
        return None

    def execute_trade(self, sig):
        sym = sig['symbol']
        if sym in self.active_positions:
            return
            
        cap_base = min(self.capital, MAX_CAPITAL_CAP)
        risk_amt = cap_base * RISK_PCT
        units = risk_amt / sig['risk']
        notional = units * sig['entry']
        margin = notional / LEVERAGE
        
        # Telegram Notification with explicit IST Time
        msg = (
            f"🎯 *NEW {sig['type']} SIGNAL DETECTED!*\n"
            f"⏰ *Time (IST):* `{format_ist_str()}`\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 *Asset:* `{sym}`\n"
            f"📍 *Entry (OTE):* `${sig['entry']:,.4f}`\n"
            f"🛑 *Stop Loss:* `${sig['sl']:,.4f}`\n"
            f"🎯 *Stage 1 (Mid):* `${sig['tp_mid']:,.4f}`\n"
            f"🏆 *TP1 (Asian Level):* `${sig['tp1']:,.4f}`\n"
            f"🚀 *TP2 (-0.27 Ext):* `${sig['tp2']:,.4f}`\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Risk:* `${risk_amt:,.2f}` (2%)\n"
            f"💼 *Margin Locked:* `${margin:,.2f}` ({LEVERAGE}x)\n"
            f"⚖️ *Wallet Balance:* `${self.capital:,.2f}`"
        )
        send_telegram(msg)
        
        self.active_positions[sym] = {
            'signal': sig,
            'units': units,
            'rem_units': units,
            'curr_sl': sig['sl'],
            'hit_mid': False,
            'hit_tp1': False
        }

    def manage_positions(self):
        closed = []
        for sym, pos in self.active_positions.items():
            df = self.fetch_candles(sym, limit=2)
            if df.empty:
                continue
            curr = df.iloc[-1]['close']
            sig = pos['signal']
            
            if sig['type'] == 'BUY':
                if curr <= pos['curr_sl']:
                    loss = (pos['curr_sl'] - sig['entry']) * pos['rem_units']
                    self.capital += loss
                    closed.append(sym)
                    send_telegram(f"🔴 *STOP LOSS HIT* on `{sym}` ({format_ist_str()})\nExit: `${pos['curr_sl']:,.4f}`\nPnL: `${loss:+,.2f}`\nNew Balance: `${self.capital:,.2f}`")
                    continue
                if not pos['hit_mid'] and (curr >= sig['tp_mid'] or curr >= sig['entry'] + sig['risk']):
                    pos['hit_mid'] = True
                    pnl = (curr - sig['entry']) * (pos['units'] * 0.30)
                    pos['rem_units'] -= (pos['units'] * 0.30)
                    pos['curr_sl'] = sig['entry']
                    self.capital += pnl
                    send_telegram(f"🎉 *STAGE 1 HIT* on `{sym}`! ({format_ist_str()})\n✅ *30% Booked:* `+${pnl:,.2f}`\n🔒 *SL Moved to Breakeven (`${sig['entry']:,.4f}`)*\n🛡️ *Trade is now 100% RISK-FREE!*")
                if not pos['hit_tp1'] and curr >= sig['tp1']:
                    pos['hit_tp1'] = True
                    pnl = (sig['tp1'] - sig['entry']) * (pos['units'] * 0.40)
                    pos['rem_units'] -= (pos['units'] * 0.40)
                    self.capital += pnl
                    send_telegram(f"🏆 *TP1 (Asian High) HIT* on `{sym}`! ({format_ist_str()})\n✅ *40% Booked:* `+${pnl:,.2f}`\nBalance: `${self.capital:,.2f}`")
                if curr >= sig['tp2']:
                    pnl = (sig['tp2'] - sig['entry']) * pos['rem_units']
                    self.capital += pnl
                    closed.append(sym)
                    send_telegram(f"🚀 *FULL TARGET (TP2) HIT* on `{sym}`! ({format_ist_str()})\n✅ *Runner Closed:* `+${pnl:,.2f}`\n💰 *Total Balance:* `${self.capital:,.2f}`")
                    continue
            else: # SELL
                if curr >= pos['curr_sl']:
                    loss = (sig['entry'] - pos['curr_sl']) * pos['rem_units']
                    self.capital += loss
                    closed.append(sym)
                    send_telegram(f"🔴 *STOP LOSS HIT* on `{sym}` ({format_ist_str()})\nExit: `${pos['curr_sl']:,.4f}`\nPnL: `${loss:+,.2f}`\nNew Balance: `${self.capital:,.2f}`")
                    continue
                if not pos['hit_mid'] and (curr <= sig['tp_mid'] or curr <= sig['entry'] - sig['risk']):
                    pos['hit_mid'] = True
                    pnl = (sig['entry'] - curr) * (pos['units'] * 0.30)
                    pos['rem_units'] -= (pos['units'] * 0.30)
                    pos['curr_sl'] = sig['entry']
                    self.capital += pnl
                    send_telegram(f"🎉 *STAGE 1 HIT* on `{sym}`! ({format_ist_str()})\n✅ *30% Booked:* `+${pnl:,.2f}`\n🔒 *SL Moved to Breakeven (`${sig['entry']:,.4f}`)*\n🛡️ *Trade is now 100% RISK-FREE!*")
                if not pos['hit_tp1'] and curr <= sig['tp1']:
                    pos['hit_tp1'] = True
                    pnl = (sig['entry'] - sig['tp1']) * (pos['units'] * 0.40)
                    pos['rem_units'] -= (pos['units'] * 0.40)
                    self.capital += pnl
                    send_telegram(f"🏆 *TP1 (Asian Low) HIT* on `{sym}`! ({format_ist_str()})\n✅ *40% Booked:* `+${pnl:,.2f}`\nBalance: `${self.capital:,.2f}`")
                if curr <= sig['tp2']:
                    pnl = (sig['entry'] - sig['tp2']) * pos['rem_units']
                    self.capital += pnl
                    closed.append(sym)
                    send_telegram(f"🚀 *FULL TARGET (TP2) HIT* on `{sym}`! ({format_ist_str()})\n✅ *Runner Closed:* `+${pnl:,.2f}`\n💰 *Total Balance:* `${self.capital:,.2f}`")
                    continue
                    
        for s in closed:
            del self.active_positions[s]

    def run_loop(self):
        send_telegram(f"🚀 *ICT 24/7 Bot Started with LOCKED India Time (IST)!*\n⏰ *Current Time:* `{format_ist_str()}`\nMonitoring BTC, ETH, SOL, DOGE.\nSend `/status` or `/time` anytime.")
        while True:
            try:
                if self.active_positions:
                    self.manage_positions()
                for sym in SYMBOLS:
                    df = self.fetch_candles(sym, limit=100)
                    if df.empty or len(df) < 30:
                        continue
                    df = self.calculate_indicators(df)
                    self.update_asian_session(sym, df)
                    sig = self.check_signals(sym, df)
                    if sig:
                        self.execute_trade(sig)
                time.sleep(POLL_INTERVAL)
            except Exception as e:
                logger.error(f"Error in bot loop: {e}")
                time.sleep(10)

# ========================================================================================
# 6. TELEGRAM COMMAND LISTENER THREAD (WITH IST COMMANDS)
# ========================================================================================
def telegram_command_listener(bot):
    if not TELEGRAM_TOKEN:
        return
    last_update_id = 0
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    logger.info("Telegram command listener thread started.")
    
    while True:
        try:
            params = {"offset": last_update_id + 1, "timeout": 30}
            resp = requests.get(url, params=params, timeout=35)
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    last_update_id = update["update_id"]
                    msg = update.get("message", {})
                    text = msg.get("text", "").strip()
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    
                    if chat_id != str(TELEGRAM_CHAT_ID):
                        continue
                        
                    if text in ["/start", "/help"]:
                        send_telegram("🤖 *ICT Judas Bot Commands:*\n• `/time` - Current Locked IST Clock\n• `/status` - Live bot status\n• `/balance` - Capital & banked profit\n• `/positions` - Active open trades")
                    elif text == "/time":
                        now_ist = get_now_ist()
                        h = now_ist.hour
                        m = now_ist.minute
                        t_m = h * 60 + m
                        in_london = (750 <= t_m <= 990)
                        in_ny = (1050 <= t_m <= 1350)
                        in_asian = (330 <= t_m <= 750)
                        curr_session = "London Killzone 🇬🇧" if in_london else ("NY Killzone 🇺🇸" if in_ny else ("Asian Session 🌏" if in_asian else "Between Sessions (Waiting)"))
                        send_telegram(f"⏰ *Locked Clock:* `{format_ist_str(now_ist)}`\n📍 *Active Session:* `{curr_session}`")
                    elif text == "/balance":
                        send_telegram(f"💼 *Wallet Balance:* `${bot.capital:,.2f}`\n🎯 *Max Cap:* `${MAX_CAPITAL_CAP:,.2f}`\n⚡ *Leverage:* `{LEVERAGE}x`\n🛡️ *Risk per Trade:* `2%`")
                    elif text == "/positions":
                        if not bot.active_positions:
                            send_telegram("ℹ️ No active positions right now. Bot is scanning markets...")
                        else:
                            p_text = "📊 *Active Positions:*\n"
                            for s, p in bot.active_positions.items():
                                p_text += f"• `{s}`: {p['signal']['type']} @ `${p['signal']['entry']:,.4f}` (SL: `${p['curr_sl']:,.4f}`)\n"
                            send_telegram(p_text)
                    elif text == "/status":
                        send_telegram(f"🟢 *Bot Status: ONLINE 24/7*\n⏰ *Locked IST:* `{format_ist_str()}`\n💼 *Capital:* `${bot.capital:,.2f}`\n📈 *Open Trades:* `{len(bot.active_positions)}`")
            time.sleep(1)
        except Exception as e:
            time.sleep(5)

# ========================================================================================
# 7. APPLICATION ENTRY POINT
# ========================================================================================
if __name__ == "__main__":
    bot_instance = ICTBot()
    
    # 1. Start HTTP Healthcheck Server in background (for Render.com)
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    # 2. Start Telegram Command Listener in background
    tg_thread = threading.Thread(target=telegram_command_listener, args=(bot_instance,), daemon=True)
    tg_thread.start()
    
    # 3. Run Main ICT Bot 24/7 Trading Loop
    bot_instance.run_loop()
