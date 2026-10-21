"""
========================================================================================
ICT ASIAN JUDAS SWING & OTE MASTER BOT - MAIN RUNNER (INR EDITION)
Delta Exchange India (api.india.delta.exchange)
Currency: Indian Rupee (INR - ₹)
Time strictly locked to Indian Standard Time (IST, UTC+5:30)
========================================================================================
"""
import time
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import config
from delta_client import DeltaClient
from strategy import StrategyEngine
import telegram_notifier

client = DeltaClient()
strategy = StrategyEngine(client)

class KeepAliveDashboardHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        """Responds to UptimeRobot HEAD ping with 200 OK to keep service alive."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        state = client.state
        trades = state.get("closed_trades", [])
        wins = sum(1 for t in trades if t.get("final_pnl_inr", 0) > 0)
        losses = sum(1 for t in trades if t.get("final_pnl_inr", 0) < 0)
        total = len(trades)
        win_rate = (wins / total * 100) if total > 0 else 0.0

        now_ist_str = config.get_now_ist().strftime('%Y-%m-%d %I:%M:%S %p')
        active_cap = state.get("active_capital_inr", config.INITIAL_CAPITAL_INR)
        banked = state.get("banked_profit_inr", 0.0)
        net_pnl = state.get("total_net_pnl_inr", 0.0)

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>ICT Asian Judas OTE Master Bot (INR)</title>
            <meta http-equiv="refresh" content="30">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0d1117; color: #c9d1d9; margin: 0; padding: 20px; }}
                .container {{ max-width: 950px; margin: 0 auto; }}
                .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #30363d; padding-bottom: 15px; margin-bottom: 20px; }}
                h2 {{ color: #58a6ff; margin: 0; }}
                .badge {{ padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 5px; }}
                .badge-green {{ background: #238636; color: white; }}
                .badge-blue {{ background: #1f6feb; color: white; }}
                .badge-orange {{ background: #d29922; color: #0d1117; }}
                .badge-purple {{ background: #8957e5; color: white; }}
                .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 25px; }}
                .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 15px; }}
                .card-title {{ font-size: 12px; color: #8b949e; text-transform: uppercase; margin-bottom: 5px; }}
                .card-val {{ font-size: 20px; font-weight: bold; color: #f0f6fc; }}
                .pos-table {{ width: 100%; border-collapse: collapse; background: #161b22; border-radius: 6px; overflow: hidden; }}
                .pos-table th, .pos-table td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #30363d; font-size: 13px; }}
                .pos-table th {{ background: #21262d; color: #8b949e; }}
                .text-green {{ color: #3fb950; font-weight: bold; }}
                .text-red {{ color: #f85149; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🎯 ICT Asian Judas OTE Master Bot (Delta India)</h2>
                    <div>
                        <span class="badge badge-purple">🇮🇳 IST: {now_ist_str}</span>
                        <span class="badge badge-green">INR (₹) EDITION</span>
                        <span class="badge badge-orange">{config.LEVERAGE}x LEVERAGE</span>
                        <span class="badge badge-blue">{'PAPER TRADING' if config.PAPER_TRADING else 'LIVE TRADING'}</span>
                    </div>
                </div>

                <div class="grid">
                    <div class="card">
                        <div class="card-title">Active INR Capital</div>
                        <div class="card-val">{config.format_inr(active_cap)}</div>
                    </div>
                    <div class="card">
                        <div class="card-title">Banked Vault (Cap ₹90L)</div>
                        <div class="card-val text-green">{config.format_inr(banked)}</div>
                    </div>
                    <div class="card">
                        <div class="card-title">Total Realized PnL</div>
                        <div class="card-val {'text-green' if net_pnl >= 0 else 'text-red'}">{'+' if net_pnl >= 0 else ''}{config.format_inr(net_pnl)}</div>
                    </div>
                    <div class="card">
                        <div class="card-title">Win Rate</div>
                        <div class="card-val">{win_rate:.1f}% ({wins}W / {losses}L)</div>
                    </div>
                </div>

                <h3>Active Positions ({len(state.get('open_positions', {}))})</h3>
                <table class="pos-table">
                    <thead>
                        <tr>
                            <th>Coin</th>
                            <th>Side</th>
                            <th>Entry (USD / INR)</th>
                            <th>SL</th>
                            <th>Rescue (+1R)</th>
                            <th>Target 1</th>
                            <th>Margin (20x INR)</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        open_pos = state.get("open_positions", {})
        if not open_pos:
            html += "<tr><td colspan='7' style='text-align: center; color: #8b949e; padding: 20px;'>No active positions. Scanning Top 5 coins...</td></tr>"
        else:
            for sym, p in open_pos.items():
                side_cls = "text-green" if p['side'] == "LONG" else "text-red"
                html += f"""
                <tr>
                    <td><b>{sym}</b></td>
                    <td class="{side_cls}">{p['side']}</td>
                    <td>${p['entry_price']:.4f} <small style='color:#8b949e'>(~₹{p.get('entry_inr_est', 0):,.2f})</small></td>
                    <td>${p['sl_price']:.4f}</td>
                    <td>${p['rescue_tp']:.4f}</td>
                    <td>${p['tp1_price']:.4f}</td>
                    <td>{config.format_inr(p.get('margin_used_inr', 0))}</td>
                </tr>
                """

        html += """
                    </tbody>
                </table>
            </div>
        </body>
        </html>
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def log_message(self, format, *args):
        return  # Suppress HTTP access noise

def run_http_server():
    server = HTTPServer((config.SERVER_HOST, config.SERVER_PORT), KeepAliveDashboardHandler)
    print(f"🌐 Keepalive Web Server listening on port {config.SERVER_PORT}")
    server.serve_forever()

def run_telegram_poller():
    while True:
        try:
            telegram_notifier.handle_telegram_updates(client)
        except Exception as e:
            pass
        time.sleep(2)

def main():
    now_ist_str = config.get_now_ist().strftime('%Y-%m-%d %I:%M:%S %p')
    active_cap = client.state.get('active_capital_inr', config.INITIAL_CAPITAL_INR)
    banked = client.state.get('banked_profit_inr', 0.0)

    print("=" * 90)
    print("🎯 ICT ASIAN JUDAS SWING & OTE MASTER BOT - DELTA EXCHANGE INDIA (INR EDITION)")
    print(f"   Mode: {'🟢 PAPER TRADING (Safe Simulation)' if config.PAPER_TRADING else '🔥 REAL TRADING'}")
    print(f"   Clock: {now_ist_str} IST (Locked UTC+5:30)")
    print(f"   Currency: Indian Rupee (INR - ₹)")
    print(f"   Active Capital: {config.format_inr(active_cap)} | Banked Vault: {config.format_inr(banked)}")
    print(f"   Leverage: {config.LEVERAGE}x | Risk Per Trade: {config.RISK_PER_TRADE_PCT*100:.1f}%")
    print(f"   Top 5 Coins: {', '.join(config.SYMBOLS)}")
    print(f"   Sessions (IST): Asian (05:30-12:30), London (12:30-16:30), NY (17:30-22:30)")
    print("=" * 90)

    # 1. Start Web Dashboard Keep-Alive thread
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    # 2. Start Telegram remote poller thread
    tg_thread = threading.Thread(target=run_telegram_poller, daemon=True)
    tg_thread.start()

    # Startup Notification to Telegram
    telegram_notifier.send_alert(
        f"🚀 *[ICT SNIPER BOT STARTED - INR EDITION]*\n"
        f"═══════════════════════\n"
        f"🇮🇳 *Clock:* `{now_ist_str}` IST\n"
        f"🇮🇳 *Currency:* `Indian Rupee (INR - ₹)`\n"
        f"💼 *Starting Capital:* `{config.format_inr(active_cap)}`\n"
        f"⚡ *Leverage:* {config.LEVERAGE}x Isolated\n"
        f"🪙 *Top 5 Coins:* `{', '.join(config.SYMBOLS)}`\n"
        f"🛡️ *Rescued Risk Management:* ACTIVE (+1.0R / BE Lock)\n"
        f"✅ Bot is actively scanning and ready for trades!"
    )

    # 3. Main 24/7 Scanning Loop
    scan_interval = 20  # scan every 20 seconds
    while True:
        try:
            # A. Manage and monitor open positions
            client.manage_positions()

            # B. Scan symbols for new setups if space available
            open_count = len(client.state.get("open_positions", {}))
            if open_count < config.MAX_CONCURRENT_TRADES:
                for symbol in config.SYMBOLS:
                    if symbol in client.state.get("open_positions", {}):
                        continue

                    candles = client.fetch_candles(symbol, resolution=config.CANDLE_RESOLUTION, limit=60)
                    if len(candles) < 25:
                        continue

                    setup = strategy.analyze_symbol(symbol, candles)
                    if setup:
                        client.open_position(setup)
                        if len(client.state.get("open_positions", {})) >= config.MAX_CONCURRENT_TRADES:
                            break

        except Exception as e:
            print(f"❌ [LOOP ERROR]: {e}")

        time.sleep(scan_interval)

if __name__ == "__main__":
    main()
