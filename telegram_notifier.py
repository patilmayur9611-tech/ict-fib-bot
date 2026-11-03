import urllib.request
import json
import datetime
import config

# Hamesha India ka time (+5:30) explicitly lock:
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def get_now_ist_str():
    return datetime.datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')

TELEGRAM_OFFSET = 0
BOT_PAUSED = False

def send_telegram_alert(message):
    """
    Sends rich formatted notification to Telegram if token is set.
    Always prints to console. Guaranteed delivery with plain-text fallback.
    """
    print(f"\n[ALERT] =========================================")
    print(message)
    print(f"=================================================\n")

    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            pass
    except Exception as e:
        # 100% BULLETPROOF FALLBACK: Send without Markdown
        try:
            plain_text = message.replace('*', '').replace('_', '').replace('`', '').replace('~', '')
            payload_plain = {
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": plain_text
            }
            req2 = urllib.request.Request(url, data=json.dumps(payload_plain).encode('utf-8'), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req2, timeout=12) as r2:
                print(f"[TELEGRAM RECOVERED] Message delivered via plain text fallback.")
        except Exception as e2:
            print(f"[TELEGRAM ERROR] Failed to send alert: {e} | Fallback Error: {e2}")

def handle_telegram_command(client, text):
    """
    Handles any incoming message or slash command with rich instant reply.
    All balances, sizing, and PnL formatted in Indian Rupees (INR ₹).
    """
    global BOT_PAUSED
    text_clean = text.strip().lower()
    sym_curr = getattr(config, 'CURRENCY_SYMBOL', '₹')
    usd_rate = getattr(config, 'USD_TO_INR', 89.0)

    bal = client.get_balance() if hasattr(client, 'get_balance') else client.portfolio.get('virtual_balance', config.VIRTUAL_INITIAL_BALANCE)
    realized = client.portfolio.get('realized_pnl', 0.0)
    mode_str = "Paper Trading (Demo)" if getattr(config, 'PAPER_TRADING', True) else "Live / Testnet API Trading"

    if text_clean in ["/start", "start", "/help", "help"]:
        help_text = (
            "🤖 *WHALE & MOMENTUM BOT ACTIVE (DELTA INDIA)*\n\n"
            "• `/status` or `/whale` - Check live status & open positions\n"
            "• `/pause` or `/pause_whale` - Pause bot\n"
            "• `/resume` or `/resume_whale` - Resume bot\n"
            "• `/reset` - Reset paper trading capital\n\n"
            f"• Mode: *{mode_str}*\n"
            f"• Current Status: *{'PAUSED ⏸️' if BOT_PAUSED else 'ACTIVE 🟢'}*\n"
            f"• Account Balance: *{sym_curr}{bal:,.2f}*\n"
            f"• Realized PnL: *{'+' if realized >= 0 else ''}{sym_curr}{realized:,.2f}*\n"
            f"• Open Positions: *{len(client.portfolio.get('open_positions', {}))}*"
        )
        send_telegram_alert(help_text)
        return

    if text_clean in ["/whale", "/status_whale", "/status", "status", "pnl", "balance", "trades", "/balance", "/pnl"]:
        open_trades = client.portfolio.get("open_positions", {})
        pos_lines = []
        for sym, p in open_trades.items():
            cur_p = p.get('current_price', p.get('entry_price', 0))
            side = p.get('side', 'LONG')
            ep = p.get('entry_price', cur_p)
            gain = ((cur_p - ep) / ep * 100) if ep > 0 and side == 'LONG' else (((ep - cur_p) / ep * 100) if ep > 0 else 0)
            size_inr = p.get('size_inr', p.get('size_usd', 0) * usd_rate)
            pos_lines.append(f"• *{sym}* [{side}]: Entry `${ep:.4f}` | Cur `${cur_p:.4f}` | Gain *{gain:+.2f}%* (Size: *{sym_curr}{size_inr:,.0f}*)")

        pos_text = "\n".join(pos_lines) if pos_lines else "None (Waiting for High-Score Whale Setup)"

        reply = (
            f"🐋 *WHALE & MOMENTUM BOT STATUS (DELTA INDIA)*\n\n"
            f"• Time (IST): *{get_now_ist_str()}*\n"
            f"• Status: *{'PAUSED ⏸️' if BOT_PAUSED else 'ACTIVE 🟢'}*\n"
            f"• Virtual Capital: *{sym_curr}{bal:,.2f}*\n"
            f"• Realized PnL: *{'+' if realized >= 0 else ''}{sym_curr}{realized:,.2f}*\n"
            f"• Open Positions ({len(open_trades)}/{config.MAX_CONCURRENT_TRADES}):\n{pos_text}\n\n"
            f"• Engine: *Model 6 (5m + 50% Retest + ATR SL + Macro Trend)*\n"
            f"• Currency: *INR ({sym_curr}) Delta India*\n"
            f"• Universe: *100% DYNAMIC* (All 230+ Delta Perps)"
        )
        send_telegram_alert(reply)
        return

    elif text_clean in ["/pause_whale", "/pause", "pause"]:
        BOT_PAUSED = True
        send_telegram_alert("⏸️ *Whale & Momentum Bot is now PAUSED.* No new positions will be opened.")
        return

    elif text_clean in ["/resume_whale", "/resume", "resume"]:
        BOT_PAUSED = False
        tf = getattr(config, 'ENTRY_TIMEFRAME', '5m')
        send_telegram_alert(f"▶️ *Whale & Momentum Bot is now RESUMED.* Scanning for {tf} sniper entries in INR (₹).")
        return

    elif text_clean in ["/reset", "reset", "/reset_portfolio"]:
        client.portfolio["virtual_balance"] = config.VIRTUAL_INITIAL_BALANCE
        client.portfolio["realized_pnl"] = 0.0
        client.portfolio["open_positions"] = {}
        client.portfolio["trade_history"] = []
        client.portfolio["cooldowns"] = {}
        client.save_portfolio()
        send_telegram_alert(f"🔄 *PORTFOLIO RESET TO INITIAL STATE!*\n\n• Capital restored to: *{sym_curr}{config.VIRTUAL_INITIAL_BALANCE:,.2f}*\n• Realized PnL: *{sym_curr}0.00*\n• Fresh start ready!")
        return

    elif text_clean in ["/ai", "/ai_ote", "ai", "/advisor", "/ai_status", "/psychology"]:
        try:
            import ai_advisor
            report = ai_advisor.get_ai_status_report()
            send_telegram_alert(report)
        except Exception as e:
            send_telegram_alert(f"⚠️ [AI ADVISOR ERROR] {e}")
        return

    elif text_clean in ["/apply", "/apply_ote", "apply"]:
        try:
            import ai_advisor
            if hasattr(ai_advisor, 'apply_pending_ai_recommendation'):
                _, res = ai_advisor.apply_pending_ai_recommendation(config)
            elif hasattr(ai_advisor, 'apply_recommendation'):
                res = ai_advisor.apply_recommendation(config)
            else:
                res = "AI Advisor module ready."
            send_telegram_alert(res)
        except Exception as e:
            send_telegram_alert(f"⚠️ [AI APPLY ERROR] {e}")
        return

    elif text_clean in ["/reject", "/reject_ote", "reject"]:
        try:
            import ai_advisor
            if hasattr(ai_advisor, 'reject_pending_ai_recommendation'):
                res = ai_advisor.reject_pending_ai_recommendation()
            elif hasattr(ai_advisor, 'reject_recommendation'):
                res = ai_advisor.reject_recommendation()
            else:
                res = "AI proposal discarded."
            send_telegram_alert(res)
        except Exception as e:
            send_telegram_alert(f"⚠️ [AI REJECT ERROR] {e}")
        return

    else:
        # Fallback for any other message (hi, hello, etc.)
        open_trades = client.portfolio.get("open_positions", {})
        reply = (
            f"👋 *Whale Bot is Online & Active (Delta India)!*\n\n"
            f"• Capital (INR): *{sym_curr}{bal:,.2f}*\n"
            f"• Realized PnL: *{'+' if realized >= 0 else ''}{sym_curr}{realized:,.2f}*\n"
            f"• Open Trades: *{len(open_trades)}*\n"
            f"• Status: *{'PAUSED ⏸️' if BOT_PAUSED else 'ACTIVE 🟢'}*\n\n"
            f"Commands: `/status` | `/pause` | `/resume` | `/reset`"
        )
        send_telegram_alert(reply)

def poll_telegram_commands(client):
    """
    Polls Telegram for incoming user commands.
    """
    global TELEGRAM_OFFSET, BOT_PAUSED
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return BOT_PAUSED

    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates?offset={TELEGRAM_OFFSET}&timeout=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            res = json.loads(r.read().decode('utf-8'))
            updates = res.get("result", [])
            for u in updates:
                TELEGRAM_OFFSET = u["update_id"] + 1
                msg = u.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "").strip()

                if chat_id != str(config.TELEGRAM_CHAT_ID) or not text:
                    continue

                handle_telegram_command(client, text)

    except Exception:
        pass

    return BOT_PAUSED

def start_telegram_polling_thread(client):
    """
    Starts high-speed dedicated background listener for Telegram messages.
    Responds in <1.5 seconds!
    """
    import threading
    import time

    def loop():
        while True:
            try:
                poll_telegram_commands(client)
            except Exception:
                pass
            time.sleep(1.5)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    print("📲 [TELEGRAM] Instant background command listener activated (1.5s response).")

def is_bot_paused():
    return BOT_PAUSED
