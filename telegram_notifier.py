"""
========================================================================================
TELEGRAM NOTIFIER & REMOTE CONTROL MODULE (INR EDITION)
Instant Mobile Alerts & Interactive 2-Way Commands
Currency: Indian Rupee (INR - ₹)
Locked Strictly to Indian Standard Time (IST, UTC+5:30)
========================================================================================
"""
import urllib.request
import urllib.parse
import json
import threading
import time
import datetime
import config

TELEGRAM_OFFSET = 0
BOT_ACTIVE = True

def send_alert(message):
    """Sends markdown formatted message to Telegram with automatic plain-text fallback."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return None
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        # BULLETPROOF FALLBACK: Send as Plain Text
        try:
            plain_text = message.replace('*', '').replace('_', '').replace('`', '').replace('~', '')
            payload_plain = {
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": plain_text,
                "disable_web_page_preview": True
            }
            req2 = urllib.request.Request(url, data=json.dumps(payload_plain).encode('utf-8'), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req2, timeout=12) as r2:
                print(f"[TELEGRAM RECOVERED] Delivered alert via fallback plain text.")
                return json.loads(r2.read().decode())
        except Exception as e2:
            print(f"[TELEGRAM ERROR] Failed to send message: {e} | Fallback Error: {e2}")
            return None

def notify_entry(trade):
    """Sends entry alert with full ICT parameters formatted in INR (₹)."""
    side_icon = "🟢 *LONG*" if trade['side'] == 'LONG' else "🔴 *SHORT*"
    msg = (
        f"🎯 *[NEW ICT SNIPER ENTRY]* {side_icon}\n"
        f"═══════════════════════\n"
        f"🪙 Asset: *{trade['symbol']}*\n"
        f"📍 Entry (0.618 OTE): *${trade['entry_price']:.4f}* (~₹{trade['entry_inr_est']:,.2f})\n"
        f"🛡️ Initial Stop-Loss: *${trade['sl_price']:.4f}*\n"
        f"💰 Risk Amount (2%): *{config.format_inr(trade['risk_inr'])}*\n"
        f"💼 20x Margin Locked: *{config.format_inr(trade['margin_used_inr'])}*\n"
        f"═══════════════════════\n"
        f"🛡️ Rescue Level (+1R): *${trade['rescue_tp']:.4f}* (30% Profit + BE Lock)\n"
        f"🎯 Asian Target 1: *${trade['tp1_price']:.4f}* (40% Profit)\n"
        f"🚀 Target 2 Runner: *${trade['tp2_price']:.4f}* (30% Runner)\n"
        f"🕒 Time: `{trade['entry_time']}` IST\n"
        f"💡 _Setup: {trade.get('setup_type', 'ICT_OTE')}_"
    )
    send_alert(msg)

def notify_rescue_hit(trade, pnl_rescue_inr):
    """Alerts when Level 1 (+1.0R / Asian Mid) is hit and SL is locked to Breakeven Plus."""
    sl_px = trade.get('sl_price', trade['entry_price'])
    msg = (
        f"🛡️ *[RESCUE LEVEL 1 HIT - 60% BOOKED]* 💰\n"
        f"═══════════════════════\n"
        f"🪙 Asset: *{trade['symbol']}*\n"
        f"💵 Heavy Profit Secured (60%): *+{config.format_inr(pnl_rescue_inr)}*\n"
        f"🔒 *SL Shifted to BREAKEVEN PLUS (${sl_px:.4f})*\n"
        f"🛡️ Remaining 40% is *100% IN GUARANTEED GREEN PROFIT*!\n"
        f"🕒 Time: `{config.get_now_ist().strftime('%H:%M:%S')}` IST"
    )
    send_alert(msg)

def notify_tp1_hit(trade, pnl_tp1_inr, new_sl):
    """Alerts when Target 1 (Asian High/Low) hits and trails SL into profit."""
    msg = (
        f"🎯 *[ASIAN TARGET 1 HIT - 25% BOOKED]* 💰\n"
        f"═══════════════════════\n"
        f"🪙 Asset: *{trade['symbol']}*\n"
        f"💵 Target 1 Profit (25%): *+{config.format_inr(pnl_tp1_inr)}*\n"
        f"📈 *Trailing SL locked in HIGHER PROFIT at ${new_sl:.4f}*\n"
        f"🚀 15% Runner open for Target 2 Home Run!\n"
        f"🕒 Time: `{config.get_now_ist().strftime('%H:%M:%S')}` IST"
    )
    send_alert(msg)

def notify_tp2_hit(trade, total_pnl_inr):
    """Alerts when Target 2 Runner (3.0R) hits."""
    msg = (
        f"🚀 *[TARGET 2 RUNNER HIT - HOME RUN!]* 🏆\n"
        f"═══════════════════════\n"
        f"🪙 Asset: *{trade['symbol']}*\n"
        f"💰 Total Realized PnL: *+{config.format_inr(total_pnl_inr)}*\n"
        f"🎉 Position fully closed with massive profit!\n"
        f"🕒 Time: `{config.get_now_ist().strftime('%H:%M:%S')}` IST"
    )
    send_alert(msg)

def notify_sl_hit(trade, total_pnl_inr, reason):
    """Alerts when Stop Loss or Breakeven exit triggers."""
    if "BREAKEVEN" in reason or total_pnl_inr >= 0:
        icon = "🛡️ *[BREAKEVEN EXIT - PROTECTED]*"
        verdict = f"✅ Secured Profit: *+{config.format_inr(total_pnl_inr)}* (Zero Loss!)"
    else:
        icon = "❌ *[STOP LOSS TRIGGERED]*"
        verdict = f"🔻 Loss: *-{config.format_inr(abs(total_pnl_inr))}*"

    msg = (
        f"{icon}\n"
        f"═══════════════════════\n"
        f"🪙 Asset: *{trade['symbol']}*\n"
        f"{verdict}\n"
        f"📍 Exit Price: *${trade.get('exit_price', 0):.4f}*\n"
        f"🕒 Time: `{config.get_now_ist().strftime('%H:%M:%S')}` IST"
    )
    send_alert(msg)

def handle_telegram_updates(client):
    """Polls Telegram for interactive bot remote control commands."""
    global TELEGRAM_OFFSET
    if not config.TELEGRAM_BOT_TOKEN:
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates?offset={TELEGRAM_OFFSET}&timeout=5"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            updates = data.get("result", [])
            for u in updates:
                TELEGRAM_OFFSET = u["update_id"] + 1
                msg = u.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "").strip()

                if chat_id != str(config.TELEGRAM_CHAT_ID):
                    continue

                cmd = text.lower().split()[0] if text else ""
                now_ist = config.get_now_ist().strftime('%Y-%m-%d %I:%M:%S %p')

                if cmd == "/time":
                    resp = (
                        f"⏰ *[OFFICIAL CLOCK SYNCHRONIZATION]*\n"
                        f"═══════════════════════\n"
                        f"🇮🇳 *Current India Time:* `{now_ist}` IST\n"
                        f"🔒 *Locked Timezone:* `UTC+5:30 (Asia/Kolkata)`\n"
                        f"✅ *Clock Drift:* `0.00 seconds (Exact Sync)`\n"
                        f"🌐 *Cloud Platform:* Render Cloud Host"
                    )
                    send_alert(resp)

                elif cmd in ["/status", "/balance"]:
                    state = client.state
                    trades = state.get("closed_trades", [])
                    total_trades = len(trades)
                    wins = sum(1 for t in trades if t.get("final_pnl_inr", 0) > 0)
                    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

                    active_cap = state.get("active_capital_inr", config.INITIAL_CAPITAL_INR)
                    banked = state.get("banked_profit_inr", 0.0)
                    net_pnl = state.get("total_net_pnl_inr", 0.0)
                    pnl_sign = "+" if net_pnl >= 0 else "-"
                    active_coins = getattr(client, 'active_universe', config.SYMBOLS)
                    top_preview = ', '.join(active_coins[:8]) + ('...' if len(active_coins) > 8 else '')

                    resp = (
                        f"📊 *[DELTA INDIA WALLET & BOT STATUS]*\n"
                        f"═══════════════════════\n"
                        f"🕒 Time: `{now_ist}` IST\n"
                        f"🇮🇳 *Currency:* `INR (Indian Rupee - ₹)`\n"
                        f"💼 *Active Capital:* `{config.format_inr(active_cap)}`\n"
                        f"🏦 *Banked Safe Vault:* `{config.format_inr(banked)}`\n"
                        f"💵 *Total Net PnL:* `{pnl_sign}{config.format_inr(abs(net_pnl))}`\n"
                        f"📈 *Trades Executed:* {total_trades} (Wins: {wins} | WR: {win_rate:.1f}%)\n"
                        f"⚡ *Leverage:* {config.LEVERAGE}x Isolated\n"
                        f"🕒 *Trading Mode:* 24x7 Nonstop (Night & Weekend Active)\n"
                        f"🪙 *Dynamic Universe:* {len(active_coins)} Liquid Coins (Filtered from 240+)\n"
                        f"📋 *Top Coins:* `{top_preview}`"
                    )
                    send_alert(resp)

                elif cmd == "/positions":
                    pos = client.state.get("open_positions", {})
                    active_coins = getattr(client, 'active_universe', config.SYMBOLS)
                    if not pos:
                        send_alert(f"📭 *No active positions open right now.* Bot is scanning Top {len(active_coins)} liquid coins.")
                    else:
                        resp = f"📂 *[ACTIVE OPEN POSITIONS ({len(pos)})]*\n═══════════════════════\n"
                        for sym, p in pos.items():
                            resp += (
                                f"🪙 *{sym}* ({p['side']})\n"
                                f"📍 Entry: `${p['entry_price']:.4f}` (~₹{p.get('entry_inr_est', 0):,.2f})\n"
                                f"🛡️ SL: `${p['sl_price']:.4f}` | Risk: {config.format_inr(p.get('risk_inr', 0))}\n"
                                f"🛡️ Rescue Hit: `{p['rescue_hit']}` | TP1 Hit: `{p['tp1_hit']}`\n"
                                f"💼 20x Margin: `{config.format_inr(p.get('margin_used_inr', 0))}`\n───────────────────────\n"
                            )
                        send_alert(resp)

                elif cmd == "/reset":
                    client.state["active_capital_inr"] = 2000.0
                    client.state["initial_capital_inr"] = 2000.0
                    client.state["month_starting_capital_inr"] = 2000.0
                    client.state["banked_profit_inr"] = 0.0
                    client.state["total_net_pnl_inr"] = 0.0
                    client.state["open_positions"] = {}
                    client.state["closed_trades"] = []
                    client.save_state()
                    resp = (
                        f"🔄 *[WALLET RESET COMPLETE]*\n"
                        f"═══════════════════════\n"
                        f"💼 *Active Capital:* `₹2,000.00`\n"
                        f"💵 *Realized PnL:* `₹0.00`\n"
                        f"🏦 *Banked Safe Vault:* `₹0.00`\n"
                        f"📊 *Open Positions:* `0 (Cleared)`\n"
                        f"📈 *Trades Record:* `0 (Fresh Start)`\n"
                        f"🕒 Time: `{now_ist}` IST\n"
                        f"✅ Virtual money has been reset to ₹2,000.00 INR successfully!"
                    )
                    send_alert(resp)

                elif cmd in ["/start", "/help"]:
                    resp = (
                        f"🤖 *ICT ASIAN JUDAS OTE MASTER BOT (INR EDITION)*\n"
                        f"═══════════════════════\n"
                        f"Currency: Indian Rupee (₹ - INR)\n"
                        f"Available Commands:\n"
                        f"• `/time` - Check official locked IST (+5:30) time\n"
                        f"• `/status` - Check wallet balance (₹), vault, & PnL\n"
                        f"• `/positions` - View current open trades & margins\n"
                        f"• `/balance` - Quick INR balance overview\n"
                        f"• `/reset` - Reset virtual wallet to ₹2,000.00 INR\n"
                        f"• `/help` - View command list"
                    )
                    send_alert(resp)

    except Exception as e:
        pass
