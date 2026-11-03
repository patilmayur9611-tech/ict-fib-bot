import json
import os
import time
import datetime
from typing import Dict, Any, Optional, Tuple

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def get_now_ist_str():
    return datetime.datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')

AI_OVERRIDES_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "ai_overrides.json"))
PSYCHOLOGY_MEMORY_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "psychology_memory.json"))
PENDING_AI_RECOMMENDATION: Optional[Dict[str, Any]] = None

# ==============================================================================
# 🧠 PERSISTENT PSYCHOLOGY MEMORY SYSTEM
# ==============================================================================
DEFAULT_MEMORY: Dict[str, Any] = {
    "version": "2.0_SMART_MONEY_PSYCHOLOGY",
    "discipline_state": "NORMAL",   # NORMAL | DEFENSIVE | HOT_STREAK
    "consecutive_losses": 0,
    "consecutive_wins": 0,
    "max_consecutive_losses": 0,
    "max_consecutive_wins": 0,
    "recent_streak": [],
    "stats": {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "realized_pnl_inr": 0.0,
        "profit_factor": 1.0
    },
    "trap_analytics": {
        "liquidity_sweep_losses": 0,
        "btc_dump_losses": 0,
        "chop_whipsaw_losses": 0,
        "decay_cut_losses": 0,
        "clean_fib_wins": 0,
        "squeeze_fuel_wins": 0
    },
    "coin_reputation": {},
    "adaptive_tuning": {
        "min_score_required": 85,
        "position_size_multiplier": 1.0,
        "cooldown_multiplier": 1.0,
        "dynamic_tp1_book_ratio": 0.75,
        "min_displacement_pct": 0.012
    },
    "learnings_log": [
        "Smart Money Institutional Psychology Engine initialized. Ready to record live trade post-mortems."
    ],
    "trade_journal": []
}

def load_psychology_memory() -> Dict[str, Any]:
    if os.path.exists(PSYCHOLOGY_MEMORY_FILE):
        try:
            with open(PSYCHOLOGY_MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure all default keys exist
                for k, v in DEFAULT_MEMORY.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception as e:
            print(f"⚠️ [PSYCHOLOGY MEMORY] Error loading file: {e}")
    return dict(DEFAULT_MEMORY)

def save_psychology_memory(data: Dict[str, Any]):
    try:
        with open(PSYCHOLOGY_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"⚠️ [PSYCHOLOGY MEMORY] Error saving file: {e}")

# ==============================================================================
# 🎯 DISCIPLINE STATE MACHINE & PARAMETER GATES
# ==============================================================================
def get_psychology_state() -> str:
    mem = load_psychology_memory()
    return mem.get("discipline_state", "NORMAL")

def get_position_size_multiplier() -> float:
    mem = load_psychology_memory()
    return float(mem.get("adaptive_tuning", {}).get("position_size_multiplier", 1.0))

def get_required_entry_score() -> int:
    mem = load_psychology_memory()
    return int(mem.get("adaptive_tuning", {}).get("min_score_required", 85))

def get_dynamic_tp1_book_ratio() -> float:
    mem = load_psychology_memory()
    return float(mem.get("adaptive_tuning", {}).get("dynamic_tp1_book_ratio", 0.75))

def is_coin_suspended(symbol: str) -> Tuple[bool, str]:
    mem = load_psychology_memory()
    rep = mem.get("coin_reputation", {}).get(symbol, {})
    if rep.get("status") == "CHOPPY_SUSPENDED":
        expiry = rep.get("suspended_until", 0)
        now = time.time()
        if now < expiry:
            rem_mins = int((expiry - now) / 60)
            return True, f"Coin suspended by AI Memory ({rem_mins}m remaining due to recent chop traps)"
        else:
            rep["status"] = "PROBATION"
            save_psychology_memory(mem)
    return False, ""

# ==============================================================================
# 🩺 AUTOMATED POST-MORTEM & SELF-LEARNING ENGINE
# ==============================================================================
def record_trade_exit(trade_record: Dict[str, Any], client=None, config_module=None):
    """
    Called whenever a position is closed (SL hit, TP hit, Early Cut, Stagnation).
    Conducts deep post-mortem, updates streaks, manages psychological discipline,
    and evolves trading parameters over time.
    """
    from telegram_notifier import send_telegram_alert

    mem = load_psychology_memory()
    symbol = trade_record.get("symbol", "UNKNOWN")
    pnl_inr = float(trade_record.get("realized_pnl_inr", 0.0))
    gain_pct = float(trade_record.get("gain_pct", 0.0))
    reason = str(trade_record.get("reason", ""))
    entry_time = float(trade_record.get("entry_time", time.time()))
    exit_time = float(trade_record.get("exit_time", time.time()))
    duration_mins = max(1, int((exit_time - entry_time) / 60))

    is_win = (pnl_inr > 0)
    now_ist = get_now_ist_str()

    # Update Global Stats
    mem["stats"]["total_trades"] += 1
    if is_win:
        mem["stats"]["wins"] += 1
    else:
        mem["stats"]["losses"] += 1
    mem["stats"]["realized_pnl_inr"] += pnl_inr
    total_t = mem["stats"]["total_trades"]
    mem["stats"]["win_rate"] = mem["stats"]["wins"] / total_t if total_t > 0 else 0.0

    # Streak Management
    mem["recent_streak"].append("WIN" if is_win else "LOSS")
    if len(mem["recent_streak"]) > 30:
        mem["recent_streak"] = mem["recent_streak"][-30:]

    # Post-Mortem Diagnosis
    diagnosis = ""
    trap_type = "NONE"

    if not is_win:
        mem["consecutive_losses"] += 1
        mem["consecutive_wins"] = 0
        mem["max_consecutive_losses"] = max(mem["max_consecutive_losses"], mem["consecutive_losses"])

        if "Early Reversal Decay" in reason:
            trap_type = "DECAY_CUT"
            mem["trap_analytics"]["decay_cut_losses"] += 1
            diagnosis = f"Early Reversal Stalled ({duration_mins}m). Cut at {gain_pct*100:.1f}% to protect capital."
        elif duration_mins <= 10:
            trap_type = "CHOP_WHIPSAW"
            mem["trap_analytics"]["chop_whipsaw_losses"] += 1
            diagnosis = f"Micro-whipsaw within {duration_mins}m. Coin lacked trend follow-through."
        elif "Sheltered Swing Stop" in reason:
            trap_type = "LIQUIDITY_SWEEP"
            mem["trap_analytics"]["liquidity_sweep_losses"] += 1
            diagnosis = "Retail Stop-Hunt swept the sheltered low before bounce."
        else:
            trap_type = "GENERAL_SL"
            diagnosis = f"Standard Stop Loss Hit: {reason}"

        # Coin Reputation Update
        c_rep = mem["coin_reputation"].setdefault(symbol, {"wins": 0, "losses": 0, "pnl_inr": 0.0, "status": "ACTIVE"})
        c_rep["losses"] += 1
        c_rep["pnl_inr"] += pnl_inr
        c_rep["last_loss_time"] = time.time()

        if c_rep["losses"] >= 2 and (c_rep["losses"] > c_rep["wins"] * 2):
            c_rep["status"] = "CHOPPY_SUSPENDED"
            c_rep["suspended_until"] = time.time() + (4 * 3600) # Suspend for 4 hours
            susp_msg = f"🧠 *[AI LEARNING]* {symbol} placed on 4-Hour Choppy Suspension after repeat losses. Eliminating low-quality noise."
            mem["learnings_log"].append(susp_msg)
            send_telegram_alert(susp_msg)

        # ----------------------------------------------------
        # 🛡️ DISCIPLINE STATE MACHINE: DEFENSIVE SHIELD
        # ----------------------------------------------------
        if mem["consecutive_losses"] >= 2:
            prev_state = mem["discipline_state"]
            mem["discipline_state"] = "DEFENSIVE"
            mem["adaptive_tuning"]["position_size_multiplier"] = 0.5  # 50% Position Sizing
            mem["adaptive_tuning"]["min_score_required"] = 92         # Ultra-selective filter
            mem["adaptive_tuning"]["cooldown_multiplier"] = 1.5       # Longer breathing room

            alert_msg = (
                f"🛡️ *[SMART MONEY PSYCHOLOGY] DEFENSIVE SHIELD ACTIVATED*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• Time (IST): *{now_ist}*\n"
                f"• Trigger: *{mem['consecutive_losses']} Consecutive Losses* (-₹{abs(pnl_inr):.2f})\n"
                f"• Post-Mortem: _{diagnosis}_\n\n"
                f"🔒 *SMART TRADER DISCIPLINE ENFORCED:*\n"
                f"1. *Zero Revenge Trading:* Cooling down market impulses.\n"
                f"2. *Risk Buffer:* Position size cut by 50% (₹2,500 budget).\n"
                f"3. *Ultra-Selective Quality:* Minimum Entry Score raised from 85 ➔ *92*.\n"
                f"• Capital safe aur protected rahega jab tak clean setup na mile!"
            )
            send_telegram_alert(alert_msg)
            mem["learnings_log"].append(f"[{now_ist}] DEFENSIVE state triggered after {mem['consecutive_losses']} losses. Halved position size.")

    else:
        mem["consecutive_wins"] += 1
        mem["consecutive_losses"] = 0
        mem["max_consecutive_wins"] = max(mem["max_consecutive_wins"], mem["consecutive_wins"])

        if "Squeeze" in reason:
            trap_type = "SQUEEZE_FUEL"
            mem["trap_analytics"]["squeeze_fuel_wins"] += 1
            diagnosis = "Short-Squeeze fuel exploited trapped shorts cleanly."
        else:
            trap_type = "CLEAN_FIB"
            mem["trap_analytics"]["clean_fib_wins"] += 1
            diagnosis = "Clean Golden Pocket retest and Trend Fib expansion."

        # Coin Reputation Update
        c_rep = mem["coin_reputation"].setdefault(symbol, {"wins": 0, "losses": 0, "pnl_inr": 0.0, "status": "ACTIVE"})
        c_rep["wins"] += 1
        c_rep["pnl_inr"] += pnl_inr
        c_rep["status"] = "PRIME_ASSET"

        # ----------------------------------------------------
        # 🟢 DISCIPLINE RECOVERY & HOT STREAK MANAGEMENT
        # ----------------------------------------------------
        if mem["discipline_state"] == "DEFENSIVE":
            mem["discipline_state"] = "NORMAL"
            mem["adaptive_tuning"]["position_size_multiplier"] = 1.0
            mem["adaptive_tuning"]["min_score_required"] = 85
            mem["adaptive_tuning"]["cooldown_multiplier"] = 1.0

            alert_msg = (
                f"🟢 *[SMART MONEY PSYCHOLOGY] RECOVERY CONFIRMED!*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• Time (IST): *{now_ist}*\n"
                f"• Winning Trade: *{symbol} (+₹{pnl_inr:.2f})*\n"
                f"• Status: Clean trend restored. Restoring standard ₹5,000 sizing & NORMAL mode."
            )
            send_telegram_alert(alert_msg)
            mem["learnings_log"].append(f"[{now_ist}] Recovery win on {symbol}. Returned to NORMAL state.")

        elif mem["consecutive_wins"] >= 3:
            mem["discipline_state"] = "HOT_STREAK"
            mem["adaptive_tuning"]["dynamic_tp1_book_ratio"] = 0.80 # Bank 80% at TP1

            alert_msg = (
                f"🔥 *[SMART MONEY PSYCHOLOGY] 3x WINNING STREAK!* 🚀\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• Consecutive Wins: *{mem['consecutive_wins']} in a row!*\n"
                f"• Overconfidence Shield: TP1 cash bank increased to *80%* to lock profits in hand."
            )
            send_telegram_alert(alert_msg)

    # ----------------------------------------------------
    # ⚙️ DYNAMIC PARAMETER SELF-HEALING (EVERY 5 TRADES)
    # ----------------------------------------------------
    if total_t > 0 and total_t % 5 == 0:
        auto_evolve_parameters(mem, config_module)

    # Journal Entry
    journal_entry = {
        "timestamp": now_ist,
        "symbol": symbol,
        "result": "WIN" if is_win else "LOSS",
        "pnl_inr": pnl_inr,
        "gain_pct": gain_pct,
        "duration_mins": duration_mins,
        "trap_type": trap_type,
        "diagnosis": diagnosis,
        "discipline_state": mem["discipline_state"]
    }
    mem["trade_journal"].append(journal_entry)
    if len(mem["trade_journal"]) > 50:
        mem["trade_journal"] = mem["trade_journal"][-50:]

    save_psychology_memory(mem)

def auto_evolve_parameters(mem: Dict[str, Any], config_module=None):
    """
    Self-healing quant logic: Checks recent patterns and fine-tunes parameters
    to permanently avoid repeat mistakes.
    """
    recent_entries = mem.get("trade_journal", [])[-10:]
    if len(recent_entries) < 5:
        return

    chop_losses = sum(1 for e in recent_entries if e.get("trap_type") == "CHOP_WHIPSAW")
    if chop_losses >= 2:
        new_disp = 0.015 # Raise displacement threshold from 1.2% to 1.5%
        mem["adaptive_tuning"]["min_displacement_pct"] = new_disp
        if config_module and hasattr(config_module, "MIN_DISPLACEMENT_LEG_PCT"):
            setattr(config_module, "MIN_DISPLACEMENT_LEG_PCT", new_disp)
        learning = f"Self-Healing: {chop_losses} chop whipsaws detected in last 10 trades. Raised minimum displacement to 1.5% to filter flat ranges."
        mem["learnings_log"].append(f"[{get_now_ist_str()}] {learning}")
        save_ai_overrides({"MIN_DISPLACEMENT_LEG_PCT": new_disp})

# ==============================================================================
# 📊 TELEGRAM STATUS REPORT (/ai_status or /ai)
# ==============================================================================
def get_ai_status_report() -> str:
    mem = load_psychology_memory()
    state = mem.get("discipline_state", "NORMAL")
    stats = mem.get("stats", {})
    t_analytics = mem.get("trap_analytics", {})
    c_losses = mem.get("consecutive_losses", 0)
    c_wins = mem.get("consecutive_wins", 0)
    tuning = mem.get("adaptive_tuning", {})
    learnings = mem.get("learnings_log", [])[-3:]

    state_emoji = "🟢" if state == "NORMAL" else ("🛡️" if state == "DEFENSIVE" else "🔥")
    wr = stats.get("win_rate", 0.0) * 100
    pnl = stats.get("realized_pnl_inr", 0.0)

    prime_coins = [s for s, d in mem.get("coin_reputation", {}).items() if d.get("status") == "PRIME_ASSET"]
    susp_coins = [s for s, d in mem.get("coin_reputation", {}).items() if d.get("status") == "CHOPPY_SUSPENDED"]

    learn_lines = "\n".join([f"• _{l}_" for l in learnings]) if learnings else "• _Monitoring market micro-structure._"

    report = (
        f"🧠 *[SMART MONEY PSYCHOLOGY & AI ADVISOR]*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Status: *{state_emoji} {state} MODE*\n"
        f"• Active Streak: *{c_wins} Wins* | *{c_losses} Losses*\n"
        f"• Total Trades: *{stats.get('total_trades', 0)}* (Win Rate: *{wr:.1f}%*)\n"
        f"• Realized PnL: *{'+' if pnl >= 0 else ''}₹{pnl:,.2f} INR*\n\n"
        f"🛡️ *CURRENT DISCIPLINE RULES:*\n"
        f"• Position Size: *{tuning.get('position_size_multiplier', 1.0)*100:.0f}%* (₹{5000*tuning.get('position_size_multiplier', 1.0):,.0f} budget)\n"
        f"• Required Quality Score: *{tuning.get('min_score_required', 85)}/100*\n"
        f"• TP1 Cash Bank Target: *{tuning.get('dynamic_tp1_book_ratio', 0.75)*100:.0f}% Cash*\n\n"
        f"🎯 *TRAP DETECTION AUDIT:*\n"
        f"• Clean Fib Wins: *{t_analytics.get('clean_fib_wins', 0)}*\n"
        f"• Squeeze Exploitations: *{t_analytics.get('squeeze_fuel_wins', 0)}*\n"
        f"• Chop Losses Filtered: *{t_analytics.get('chop_whipsaw_losses', 0)}*\n\n"
        f"🏆 *COIN REPUTATION:*\n"
        f"• Prime Winners: *{', '.join(prime_coins) if prime_coins else 'Calibrating...'}*\n"
        f"• Suspended Traps: *{', '.join(susp_coins) if susp_coins else 'None (Clean)'}*\n\n"
        f"💡 *RECENT AI LEARNINGS:*\n"
        f"{learn_lines}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    return report

# ==============================================================================
# ⚙️ BACKWARD COMPATIBILITY HELPERS
# ==============================================================================
def load_ai_overrides(config_module):
    if os.path.exists(AI_OVERRIDES_FILE):
        try:
            with open(AI_OVERRIDES_FILE, "r", encoding="utf-8") as f:
                overrides = json.load(f)
            for k, v in overrides.items():
                if hasattr(config_module, k):
                    setattr(config_module, k, v)
            print(f"🤖 [AI ADVISOR] Loaded {len(overrides)} approved overrides.")
        except Exception as e:
            print(f"⚠️ [AI ADVISOR] Failed to load overrides: {e}")

def save_ai_overrides(overrides: Dict[str, Any]):
    try:
        with open(AI_OVERRIDES_FILE, "w", encoding="utf-8") as f:
            json.dump(overrides, f, indent=4)
    except Exception as e:
        print(f"⚠️ [AI ADVISOR] Failed to save overrides: {e}")

def evaluate_performance(client) -> Dict[str, Any]:
    mem = load_psychology_memory()
    stats = mem.get("stats", {})
    return {
        "should_trigger": mem.get("discipline_state") == "DEFENSIVE",
        "reason": f"Discipline State: {mem.get('discipline_state', 'NORMAL')}",
        "win_rate": stats.get("win_rate", 0.0),
        "profit_factor": stats.get("profit_factor", 1.0)
    }

def apply_pending_ai_recommendation(config_module) -> Tuple[bool, str]:
    return True, "✅ AI Psychology & Discipline settings already active in live memory!"

def reject_pending_ai_recommendation() -> str:
    return "ℹ️ Settings active in live memory."

def get_pending_summary() -> Optional[str]:
    return None

get_pending_recommendation_summary = get_pending_summary
apply_recommendation = lambda cfg: apply_pending_ai_recommendation(cfg)[1]
reject_recommendation = reject_pending_ai_recommendation
