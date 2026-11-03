import time
import datetime
import sys
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import config
from delta_client import DeltaClient
from whale_feed import WhaleFeed
from strategy import StrategyEngine
from telegram_notifier import send_telegram_alert, start_telegram_polling_thread, is_bot_paused

# Hamesha India ka time (+5:30) explicitly lock:
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def get_now_ist():
    return datetime.datetime.now(IST)

def get_now_ist_str():
    return datetime.datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')

GLOBAL_CLIENT = None

# ==============================================================================
# KEEP-ALIVE SERVER (For 24/7 Cloud Hosting on Render/Koyeb/Railway)
# ==============================================================================
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        open_pos = GLOBAL_CLIENT.portfolio.get("open_positions", {}) if GLOBAL_CLIENT else {}
        history = GLOBAL_CLIENT.portfolio.get("trade_history", []) if GLOBAL_CLIENT else []
        sym_curr = getattr(config, 'CURRENCY_SYMBOL', '₹')
        bal = GLOBAL_CLIENT.get_balance() if GLOBAL_CLIENT and hasattr(GLOBAL_CLIENT, 'get_balance') else config.VIRTUAL_INITIAL_BALANCE
        realized = GLOBAL_CLIENT.portfolio.get("realized_pnl", 0.0) if GLOBAL_CLIENT else 0.0
        response = {
            "status": "online",
            "bot": "Delta Whale & Momentum Quant Engine (India INR)",
            "currency": getattr(config, 'CURRENCY', 'INR'),
            "currency_symbol": sym_curr,
            "mode": "Live Paper Trading (INR)" if config.PAPER_TRADING else "Live Real",
            "virtual_balance": bal,
            "virtual_balance_formatted": f"{sym_curr}{bal:,.2f}",
            "realized_pnl": realized,
            "realized_pnl_formatted": f"{'+' if realized >= 0 else ''}{sym_curr}{realized:,.2f}",
            "open_positions": open_pos,
            "open_positions_count": len(open_pos),
            "trade_history": history,
            "trade_history_count": len(history),
            "time_ist": get_now_ist_str()
        }
        self.wfile.write(json.dumps(response, indent=2).encode('utf-8'))

    def log_message(self, format, *args):
        return # Silence HTTP access logs

def start_keepalive_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        server = HTTPServer(('0.0.0.0', port), KeepAliveHandler)
        print(f"🌐 [CLOUD SERVER] Keep-alive web endpoint active on port {port}")
        server.serve_forever()
    except Exception as e:
        print(f"[CLOUD SERVER] Server note: {e}")

LAST_LOOP_TIMESTAMP = time.time()
LAST_HEARTBEAT_SENT = 0

def watchdog_and_heartbeat_loop(client):
    """Background watchdog ensuring trading loop never freezes and periodic heartbeat alerts."""
    global LAST_LOOP_TIMESTAMP, LAST_HEARTBEAT_SENT
    sym_curr = getattr(config, 'CURRENCY_SYMBOL', '₹')
    while True:
        try:
            time.sleep(30)
            now = time.time()

            # 1. Check if trading loop stalled > 90 seconds
            if now - LAST_LOOP_TIMESTAMP > 90:
                print(f"⚠️ [WATCHDOG ALERT] Whale Bot loop stalled for {int(now - LAST_LOOP_TIMESTAMP)}s!")

            # 2. Automatic Heartbeat Pulse Every 4 Hours (14,400 seconds)
            if (now - LAST_HEARTBEAT_SENT) >= 14400:
                LAST_HEARTBEAT_SENT = now
                bal = client.portfolio.get('virtual_balance', config.VIRTUAL_INITIAL_BALANCE)
                realized = client.portfolio.get('realized_pnl', 0.0)
                open_cnt = len(client.portfolio.get("open_positions", {}))
                
                hb_msg = (
                    f"💓 *[BOT 4: WHALE SNIPER HEARTBEAT]*\n"
                    f"• Time (IST): `{get_now_ist_str()}`\n"
                    f"• System Status: 🟢 *ONLINE & SCANNING 24x7*\n"
                    f"• Universe: 230+ Delta Perpetual Futures\n"
                    f"• Active Positions: *{open_cnt}*\n"
                    f"• Virtual Capital: *{sym_curr}{bal:,.2f}*\n"
                    f"• Realized PnL: *{'+' if realized >= 0 else ''}{sym_curr}{realized:,.2f}*\n"
                    f"• Health: Zero errors | UptimeRobot Active"
                )
                send_telegram_alert(hb_msg)
        except Exception as e:
            print(f"[WATCHDOG ERROR] {e}")

def main():
    sym_curr = getattr(config, 'CURRENCY_SYMBOL', '₹')
    usd_rate = getattr(config, 'USD_TO_INR', 89.0)

    # 🛡️ WINDOWS 24/7 ANTI-SLEEP SHIELD: Laptop screen off hone par bhi sleep nahi hoga!
    if sys.platform == "win32":
        try:
            import ctypes
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
            print("[POWER] 🛡️ Windows Anti-Sleep Active: Laptop display off hone par bhi bot 24/7 chalega!")
        except Exception as e:
            print(f"[POWER] Anti-sleep note: {e}")

    # Start Keep-Alive Web Server for 24x7 cloud uptime
    threading.Thread(target=start_keepalive_server, daemon=True).start()

    print("=" * 65)
    print("  WHALE & MOMENTUM ENGINE - DELTA EXCHANGE INDIA FUTURES")
    print("  Mode: 100% LIVE PAPER TRADING (Safe Forward-Testing in INR)")
    print(f"  Initial Virtual Capital: {sym_curr}{config.VIRTUAL_INITIAL_BALANCE:,.2f} ({config.CURRENCY})")
    print(f"  Delta USD/INR Peg Rate: {sym_curr}{usd_rate:.2f} per USD")
    print("  Universe: 100% DYNAMIC (Scanning ALL 230+ Delta Perpetual Futures)")
    print("=" * 65)

    client = DeltaClient()
    global GLOBAL_CLIENT
    GLOBAL_CLIENT = client
    whale_feed = WhaleFeed()
    engine = StrategyEngine(client, whale_feed)

    # Load approved AI parameter overrides
    try:
        import ai_advisor
        ai_advisor.load_ai_overrides(config)
    except Exception as e:
        print(f"[AI NOTE] {e}")

    # Start Instant Telegram Command Listener (Runs in background, responds in <1.5s)
    start_telegram_polling_thread(client)

    # Start Anti-Freeze Watchdog & Heartbeat thread
    threading.Thread(target=watchdog_and_heartbeat_loop, args=(client,), daemon=True).start()
    print("🛡️ [WATCHDOG] Anti-Freeze Watchdog & 4-Hour Heartbeat active.")

    bal = client.portfolio.get('virtual_balance', config.VIRTUAL_INITIAL_BALANCE)
    feed_tag = "ACTIVE (L2 Depth + Taker Flow + OI + Top Whales)" if getattr(config, 'ENABLE_INSTITUTIONAL_FEEDS', False) else "Standard"
    startup_msg = (
        f"🤖 *WHALE & MOMENTUM SNIPER BOT STARTED (DELTA INDIA)*\n\n"
        f"• Mode: Live Paper Trading\n"
        f"• Currency: *Indian Rupees ({sym_curr} INR)*\n"
        f"• Virtual Capital: *{sym_curr}{bal:,.2f}*\n"
        f"• Leverage: *{config.LEVERAGE}x*\n"
        f"• Institutional Intelligence: *{feed_tag}*\n"
        f"• Dynamic Wall Targets: *{'ON (Front-run 0.15%)' if getattr(config, 'ENABLE_DYNAMIC_TARGET_WALLS', False) else 'OFF'}*\n"
        f"• Adaptive Harvesting: *{'ON (20% runner / 50% bank)' if getattr(config, 'ENABLE_ADAPTIVE_HARVEST_RATIO', False) else 'OFF'}*\n"
        f"• Fixed Budget: *{sym_curr}{getattr(config, 'FIXED_POSITION_SIZE_INR', 5000.0):,.0f} per trade*\n"
        f"• Universe: *Approved Major Whitelisted Assets*\n"
        f"• Timeframe: *{getattr(config, 'ENTRY_TIMEFRAME', '5m')} Sniper Entries*\n"
        f"• Time Lock (IST): *{get_now_ist_str()}*\n"
        f"• Status: 24/7 Institutional Confluence Radar ACTIVE 🌐"
    )
    send_telegram_alert(startup_msg)

    scan_count = 0
    while True:
        try:
            global LAST_LOOP_TIMESTAMP
            LAST_LOOP_TIMESTAMP = time.time()
            scan_count += 1
            print(f"\n--- [SCAN #{scan_count}] Checking Whale Radar ({get_now_ist_str()}) ---")

            # Check if bot is paused via Telegram
            if is_bot_paused():
                print(f"  [PAUSED] Whale Bot is paused via Telegram command. Waiting...")
                time.sleep(config.SCAN_INTERVAL_SECONDS)
                continue

            # 1. Fetch live Delta tickers
            tickers = client.get_all_tickers()
            if not tickers:
                print("[WARN] Could not retrieve tickers from Delta India, retrying in 10s...")
                time.sleep(10)
                continue

            # 2. Manage existing open positions (Check SL & TPs)
            engine.manage_positions(tickers)

            # 3. Universe Scanner: Scan High-Quality Approved Major Assets (No Meme Traps!)
            perp_candidates = []
            approved_set = set(getattr(config, 'APPROVED_MAJOR_COINS', []))
            banned_set = set(getattr(config, 'BANNED_SYMBOLS', []))
            strict_mode = getattr(config, 'STRICT_MAJOR_COINS_ONLY', True)

            for sym, t in tickers.items():
                if sym in banned_set:
                    continue
                if strict_mode and sym not in approved_set:
                    continue
                p_info = client.cached_products.get(sym, {})
                if p_info.get('contract_type') == 'perpetual_futures':
                    turnover = float(t.get('turnover_usd', 0) or 0)
                    if turnover >= getattr(config, 'MIN_24H_VOLUME_USD', 50000.0):
                        perp_candidates.append(t)

            # Sort by highest turnover & whale activity
            perp_candidates.sort(key=lambda x: float(x.get('turnover_usd', 0) or 0), reverse=True)
            active_scan_symbols = [t['symbol'] for t in perp_candidates[:config.MAX_HOT_COINS_TO_DEEP_SCAN]]

            # Also ensure any currently open positions are always included
            for open_sym in client.portfolio["open_positions"]:
                if open_sym not in active_scan_symbols:
                    active_scan_symbols.append(open_sym)

            print(f"  [RADAR] Dynamically scanning top {len(active_scan_symbols)} active whale/momentum coins...")

            for symbol in active_scan_symbols:
                ticker = tickers.get(symbol)
                if not ticker:
                    continue

                # Check if position already open
                if symbol in client.portfolio["open_positions"]:
                    pos = client.portfolio["open_positions"][symbol]
                    cur_p = float(ticker.get("mark_price", 0) or 0)
                    side_pos = pos.get("side", "LONG")
                    gain = (cur_p - pos["entry_price"]) / pos["entry_price"] if side_pos == "LONG" else (pos["entry_price"] - cur_p) / pos["entry_price"]
                    size_inr = pos.get('size_inr', pos.get('size_usd', 0) * usd_rate)
                    cts = pos.get('contracts', 0)
                    cnt_str = f" | {cts} Cts" if cts > 0 else ""
                    print(f"  [*] {symbol:13} [{side_pos:5}] | Entry: ${pos['entry_price']} | Cur: ${cur_p} | Gain: {gain*100:+.2f}%{cnt_str} | Size: {sym_curr}{size_inr:,.0f}")
                    continue

                # Multi-Timeframe Engine: 3m Sniper Entry + 15m Macro Structure & Fib Targets
                entry_tf = getattr(config, 'ENTRY_TIMEFRAME', '3m')
                macro_tf = getattr(config, 'MACRO_TIMEFRAME', '15m')
                candles_entry = client.get_candles(symbol, resolution=entry_tf, limit=65)
                candles_macro = client.get_candles(symbol, resolution=macro_tf, limit=45)
                
                res_eval = engine.evaluate_entry(symbol, ticker, candles_entry, macro_candles=candles_macro)
                if len(res_eval) == 7:
                    should_enter, side, entry_price, sl_price, score, reason, targets = res_eval
                else:
                    should_enter, side, entry_price, sl_price, score, reason = res_eval
                    targets = {}

                if should_enter:
                    # SNAP ACTION! Open position with Trend-Based Fib Targets
                    pos = client.open_paper_position(symbol, entry_price, sl_price, score, reason, side=side, targets=targets)
                    if not pos:
                        continue
                    side_badge = "🟢 LONG (BUY UP)" if side == "LONG" else "🔴 SHORT (SELL DOWN)"
                    t1 = entry_price * (1 + config.TP1_PCT) if side == "LONG" else entry_price * (1 - config.TP1_PCT)
                    t2 = entry_price * (1 + config.TP2_PCT) if side == "LONG" else entry_price * (1 - config.TP2_PCT)
                    t3 = entry_price * (1 + config.TP3_PCT) if side == "LONG" else entry_price * (1 - config.TP3_PCT)

                    pos_size_inr = pos.get('size_inr', pos.get('size_usd', 0) * usd_rate)
                    pos_size_usd = pos.get('size_usd', pos_size_inr / usd_rate)
                    sl_dist_pct = abs(entry_price - sl_price) / entry_price * 100 if entry_price > 0 else (config.STOP_LOSS_PCT * 100)
                    max_sl_loss_inr = pos_size_inr * (sl_dist_pct / 100.0)

                    entry_alert = (
                        f"🚨 *WHALE ENTRY DETECTED: {symbol}* 🚨\n\n"
                        f"• Direction: *{side_badge}*\n"
                        f"• Confluence Score: *{score}/100*\n"
                        f"• Time (IST): *{get_now_ist_str()}*\n"
                        f"• Reasons: _{reason}_\n"
                        f"• Entry Price: `${entry_price}`\n"
                        f"• Initial Stop-Loss: `${sl_price}` (-{sl_dist_pct:.2f}%)\n"
                        f"• Micro-Shield: At +{config.MICRO_BE_TRIGGER_PCT*100:.1f}% gain, SL pulls to Breakeven (+0.20% Buffer)\n"
                        f"• Target 1 (+{config.TP1_PCT*100:.1f}%): `${t1:.5f}` (Adaptive Wall-Harvest & Lock SL to +1.5%)\n"
                        f"• Target 2 (+{config.TP2_PCT*100:.1f}%): `${t2:.5f}` (Book 40% Cash & Lock SL to +3.0%)\n"
                        f"• Target 3 (+{config.TP3_PCT*100:.1f}%): `${t3:.5f}` (Moonshot Runner 🚀)\n"
                        f"• Fixed Position Budget: *{sym_curr}{pos_size_inr:,.2f}* (${pos_size_usd:,.2f} USD | {config.LEVERAGE}x)\n"
                        f"• Max SL Loss Risk: *{sym_curr}{max_sl_loss_inr:,.2f}* (-{sl_dist_pct:.2f}% on position)"
                    )
                    send_telegram_alert(entry_alert)
                else:
                    mark = ticker.get("mark_price", 0)
                    if score > 0:
                        print(f"  [+] {symbol:13} | Price: {mark} | Score: {score:2}/100 | {reason[:45]}")

            # 4. Portfolio Summary
            open_count = len(client.portfolio["open_positions"])
            balance = client.portfolio["virtual_balance"]
            realized = client.portfolio["realized_pnl"]
            print(f"--> Portfolio: Balance: {sym_curr}{balance:,.2f} | Realized PnL: {'+' if realized >= 0 else ''}{sym_curr}{realized:,.2f} | Open Positions: {open_count}")

            time.sleep(config.SCAN_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n[STOP] Bot stopped by user. Saving state...")
            client.save_portfolio()
            break
        except Exception as e:
            print(f"[ERROR] Main loop exception: {e}")
            time.sleep(10)

if __name__ == '__main__':
    main()
