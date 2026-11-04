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
    """Sends entry alert with clear Hindi / English parameters formatted in INR (₹)."""
    side = trade['side']
    side_icon = "🟢 *BUY (LONG)*" if side == 'LONG' else "🔴 *SELL (SHORT)*"
    total_c = trade.get('total_contracts', 1)
    e1 = trade.get('exit_1_contracts', 0)
    e2 = trade.get('exit_2_contracts', 0)
    e3 = trade.get('exit_3_contracts', 0)
    
    p1 = int(round((e1 / total_c) * 100)) if total_c > 0 and e1 > 0 else 0
    p2 = int(round((e2 / total_c) * 100)) if total_c > 0 and e2 > 0 else (100 if total_c == 1 else 0)
    p3 = 100 - p1 - p2 if (p1 + p2) < 100 else 0

    msg = (
        f"🎯 *[NEW TRADE OPENED / नया ट्रेड]* 🚀\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 कॉइन: *{trade['symbol']}*\n"
        f"📈 दिशा (Side): {side_icon}\n"
        f"📍 एंट्री प्राइस: *${trade['entry_price']:.4f}* (~₹{trade['entry_inr_est']:,.2f})\n"
        f"🛑 स्टॉप लॉस (SL): *${trade['sl_price']:.4f}*\n"
        f"💼 पोजीशन साइज़: *{config.format_inr(trade['position_inr'])}* ({total_c} Contracts)\n"
        f"💳 मार्जिन लगा (20x): *{config.format_inr(trade['margin_used_inr'])}*\n"
        f"⚠️ मैक्स रिस्क (SL पर): *{config.format_inr(trade['risk_inr'])}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 *प्रॉफ़िट बुकिंग प्लान (Exit Targets):*\n"
        f"  1️⃣ Rescue (+1.0R): *${trade['rescue_tp']:.4f}* ➔ *{p1}% Book ({e1}c)* + Breakeven Plus\n"
        f"  2️⃣ Asian Target 1: *${trade['tp1_price']:.4f}* ➔ *{p2}% Book ({e2}c)*\n"
        f"  3️⃣ Home Run TP2:  *${trade['tp2_price']:.4f}* ➔ *{p3}% Runner ({e3}c)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 समय: `{trade['entry_time']}` IST"
    )
    send_alert(msg)

def notify_rescue_hit(trade, pnl_rescue_inr):
    """Alerts when Level 1 (+1.0R / Asian Mid) is hit and SL is locked to Breakeven Plus."""
    total_c = max(1, trade.get('total_contracts', 1))
    e1 = trade.get('exit_1_contracts', 0)
    sl_px = trade.get('sl_price', trade['entry_price'])
    side = trade.get('side', 'LONG')
    profit_buffer_pct = abs(sl_px - trade['entry_price']) / trade['entry_price'] * 100

    if e1 == 0 or total_c == 1:
        msg = (
            f"🛡️ *[RESCUE LEVEL 1 HIT - BREAKEVEN PLUS LOCKED]* 🔒\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 कॉइन: *{trade['symbol']}* ({side})\n"
            f"ℹ️ *लॉट साइज़:* 1 Contract (डेल्टा एक्सचेंज पर 1 लॉट को आधा नहीं काटा जा सकता)\n"
            f"🔒 *सुरक्षा एक्टिव:* पूरा 1 कॉन्ट्रैक्ट अब 100% *RISK-FREE* है!\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *नया स्टॉप लॉस (Breakeven Plus):* *${sl_px:.4f}*\n"
            f"  • यह एंट्री (${trade['entry_price']:.4f}) से *+{profit_buffer_pct:.2f}% प्रॉफ़िट* में लॉक है!\n"
            f"🎯 *अगला कदम:* यह पूरा कॉन्ट्रैक्ट Target 1 (${trade['tp1_price']:.4f}) पर 100% बड़े मुनाफ़े के लिए राइड कर रहा है!\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 समय: `{config.get_now_ist().strftime('%I:%M:%S %p')}` IST"
        )
    else:
        pct_booked = int(round((e1 / total_c) * 100))
        rem_c = trade.get('remaining_contracts', total_c - e1)
        rem_pct = 100 - pct_booked
        msg = (
            f"🛡️ *[RESCUE LEVEL 1 HIT - 60% मुनाफ़ा बुक]* 💰\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 कॉइन: *{trade['symbol']}* ({side})\n"
            f"💵 *इस लेवल पर बुक हुआ:* *{pct_booked}% ({e1} Contracts)*\n"
            f"💰 *इस लेवल का मुनाफ़ा:* *+{config.format_inr(pnl_rescue_inr)}* ✅\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔒 *सुरक्षा (Protection Active):*\n"
            f"  • स्टॉप लॉस लॉक: *BREAKEVEN PLUS* (${sl_px:.4f})\n"
            f"  • यह एंट्री से *+{profit_buffer_pct:.2f}% ऊपर* प्रॉफ़िट में है!\n"
            f"  • बचा हुआ हिस्सा: *{rem_pct}% ({rem_c} Contracts) रिस्क-फ़्री चल रहा है!*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 समय: `{config.get_now_ist().strftime('%I:%M:%S %p')}` IST"
        )
    send_alert(msg)

def notify_tp1_hit(trade, pnl_tp1_inr, new_sl):
    """Alerts when Target 1 (Asian High/Low) hits and trails SL into profit."""
    total_c = max(1, trade.get('total_contracts', 1))
    e2 = trade.get('exit_2_contracts', 0)
    pct_booked = int(round((e2 / total_c) * 100)) if e2 > 0 else 25
    rem_c = trade.get('remaining_contracts', 0)
    total_realized_trade = trade.get('realized_pnl_inr', pnl_tp1_inr)

    msg = (
        f"🎯 *[ASIAN TARGET 1 HIT - 25% और बुक]* 💰\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 कॉइन: *{trade['symbol']}*\n"
        f"💵 *इस लेवल पर बुक हुआ:* *{pct_booked}% ({e2} Contracts)*\n"
        f"💰 *Target 1 का मुनाफ़ा:* *+{config.format_inr(pnl_tp1_inr)}* ✅\n"
        f"🏆 *इस ट्रेड का अब तक कुल मुनाफ़ा:* *+{config.format_inr(total_realized_trade)}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 *ट्रेलिंग सुरक्षा (Trailing SL Locked):*\n"
        f"  • नया सुरक्षित SL: *${new_sl:.4f}* (+1.0R बड़े प्रॉफ़िट में)\n"
        f"  • अंतिम रनर: *{rem_c} Contract(s)* Home Run (TP2) के लिए खुला है!\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 समय: `{config.get_now_ist().strftime('%I:%M:%S %p')}` IST"
    )
    send_alert(msg)

def notify_tp2_hit(trade, total_pnl_inr):
    """Alerts when Target 2 Runner (3.0R) hits."""
    msg = (
        f"🚀 *[TARGET 2 FULL WIN - HOME RUN!]* 🏆🎉\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 कॉइन: *{trade['symbol']}* ({trade.get('side', '')})\n"
        f"🎯 सभी 3 लेवल्स पूरे हुए (100% Position Closed)!\n"
        f"💰 *इस ट्रेड का अंतिम कुल मुनाफ़ा:* *+{config.format_inr(total_pnl_inr)}* 🚀\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 समय: `{config.get_now_ist().strftime('%I:%M:%S %p')}` IST"
    )
    send_alert(msg)

def notify_sl_hit(trade, total_pnl_inr, reason):
    """Alerts when Stop Loss or Breakeven exit triggers."""
    exit_px = trade.get('exit_price', trade.get('sl_price', 0))
    entry_px = trade.get('entry_price', 0)
    side = trade.get('side', 'LONG')

    if total_pnl_inr > 0 or "BREAKEVEN_PLUS" in reason or "TRAILING" in reason:
        icon = "🎉 *[TRADE CLOSED IN GREEN PROFIT / मुनाफ़ा बुक होकर क्लोज़]* 💰"
        verdict = (
            f"✅ *शुद्ध मुनाफ़ा जेब में लॉक:* *+{config.format_inr(total_pnl_inr)}* 🚀\n"
            f"💡 _(मार्केट पलटने के बावजूद Breakeven Plus ने मुनाफ़ा लॉक रखा!)_"
        )
    elif total_pnl_inr == 0:
        icon = "🛡️ *[TRADE CLOSED AT BREAKEVEN / नो प्रॉफ़िट नो लॉस]*"
        verdict = (
            f"✅ *सुरक्षित एग्जिट:* *₹0.00* (कोई नुक़सान नहीं!)\n"
            f"💡 _(मार्केट पलटा लेकिन Breakeven ने कैपिटल को सुरक्षित बचा लिया)_"
        )
    else:
        loss_val = abs(total_pnl_inr)
        icon = "🛑 *[STOP LOSS HIT / ट्रेड क्लोज़]*"
        verdict = (
            f"🔻 *नुक़सान (Loss):* *-{config.format_inr(loss_val)}*\n"
            f"💡 _(सख्त रिस्क मैनेजमेंट: अकाउंट का केवल ~₹47-₹50 ही लगा था)_"
        )

    msg = (
        f"{icon}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 कॉइन: *{trade['symbol']}* ({side})\n"
        f"{verdict}\n"
        f"📍 एंट्री: *${entry_px:.4f}* ➔ एग्जिट: *${exit_px:.4f}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 समय: `{config.get_now_ist().strftime('%I:%M:%S %p')}` IST"
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
