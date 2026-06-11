"""
模拟交易（Paper Trading）
跟随实盘信号自动开平仓，记录结果到 paper_trades.json。
参数：初始资金 10000U，单笔风险 1%，杠杆上限 5x，最长持仓 3 天。
运行周期：2026-06-11 ~ 2026-06-16（5 天）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

PAPER_FILE      = Path(__file__).parent / "paper_trades.json"
INITIAL_CAPITAL = 10_000.0
RISK_PER_TRADE  = 0.01    # 每笔风险占当前资金比例
MAX_LEVERAGE    = 5.0     # 杠杆上限
MAX_HOLD_DAYS   = 3       # 时间止损（天）
START_DATE      = "2026-06-11"
END_DATE        = "2026-06-16"


# ── I/O ─────────────────────────────────────────────────────────────────────

def _load() -> dict:
    if PAPER_FILE.exists():
        try:
            return json.loads(PAPER_FILE.read_text())
        except Exception:
            pass
    return _empty_state()


def _empty_state() -> dict:
    return {
        "summary": {
            "start_date":      START_DATE,
            "end_date":        END_DATE,
            "initial_capital": INITIAL_CAPITAL,
            "current_capital": INITIAL_CAPITAL,
            "total_trades":    0,
            "win_trades":      0,
            "loss_trades":     0,
            "win_rate":        0.0,
            "total_pnl_pct":   0.0,
        },
        "open_positions": [],
        "closed_trades":  [],
    }


def _save(state: dict) -> None:
    PAPER_FILE.write_text(
        json.dumps(state, default=str, indent=2, ensure_ascii=False)
    )


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(str(s))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _update_summary(state: dict) -> None:
    closed = state["closed_trades"]
    s = state["summary"]
    s["total_trades"] = len(closed)
    s["win_trades"]   = sum(1 for t in closed if t["pnl_usdt"] >= 0)
    s["loss_trades"]  = sum(1 for t in closed if t["pnl_usdt"] < 0)
    s["win_rate"]     = round(s["win_trades"] / len(closed) * 100, 1) if closed else 0.0
    s["total_pnl_pct"] = round(
        (s["current_capital"] - s["initial_capital"]) / s["initial_capital"] * 100, 2
    )


# ── 核心操作 ─────────────────────────────────────────────────────────────────

def open_position(
    symbol: str,
    direction: str,
    entry_price: float,
    stop_price: float,
    tp_price: float,
    entry_time: str,
) -> None:
    """跟随信号开模拟仓；已有同品种同方向持仓则跳过。"""
    state = _load()

    if any(p["symbol"] == symbol and p["direction"] == direction
           for p in state["open_positions"]):
        log.info(f"[Paper] {symbol} {direction} 已有持仓，跳过开仓")
        return

    capital       = state["summary"]["current_capital"]
    stop_dist_pct = abs(entry_price - stop_price) / entry_price
    if stop_dist_pct < 1e-6:
        log.warning(f"[Paper] {symbol} 止损距离过小，跳过")
        return

    # 目标：止损恰好亏掉 1% 资金；杠杆上限 5x
    leverage_raw  = RISK_PER_TRADE / stop_dist_pct
    leverage      = min(leverage_raw, MAX_LEVERAGE)
    position_usdt = round(capital * leverage, 2)
    qty           = round(position_usdt / entry_price, 6)

    state["open_positions"].append({
        "symbol":        symbol,
        "direction":     direction,
        "entry_time":    str(entry_time),
        "entry_price":   entry_price,
        "stop_price":    stop_price,
        "tp_price":      tp_price,
        "qty":           qty,
        "position_usdt": position_usdt,
        "leverage":      round(leverage, 2),
    })
    _save(state)
    log.info(
        f"[Paper] 开仓 {symbol} {direction} @ {entry_price:.2f}  "
        f"qty={qty:.4f}  lev={leverage:.1f}x  notional={position_usdt:.0f}U"
    )


def check_positions(
    symbol: str,
    current_price: float,
    current_time: Optional[datetime] = None,
) -> None:
    """用最新收盘价检查该品种所有持仓，触发止盈/止损/时间止损则平仓。"""
    state = _load()
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    remaining: list[dict] = []
    for pos in state["open_positions"]:
        if pos["symbol"] != symbol:
            remaining.append(pos)
            continue

        direction  = pos["direction"]
        hold_days  = (current_time - _parse_dt(pos["entry_time"])).total_seconds() / 86400

        if direction == "long":
            hit_tp = current_price >= pos["tp_price"]
            hit_sl = current_price <= pos["stop_price"]
        else:
            hit_tp = current_price <= pos["tp_price"]
            hit_sl = current_price >= pos["stop_price"]

        if hit_tp:
            _close(state, pos, pos["tp_price"], "tp", current_time)
        elif hit_sl:
            _close(state, pos, pos["stop_price"], "sl", current_time)
        elif hold_days >= MAX_HOLD_DAYS:
            _close(state, pos, current_price, "time_sl", current_time)
        else:
            remaining.append(pos)

    state["open_positions"] = remaining
    _save(state)


def _close(
    state: dict,
    pos: dict,
    exit_price: float,
    exit_reason: str,
    exit_time: datetime,
) -> None:
    direction     = pos["direction"]
    entry_price   = pos["entry_price"]
    position_usdt = pos["position_usdt"]
    capital       = state["summary"]["current_capital"]

    price_chg = (exit_price - entry_price) / entry_price
    if direction == "short":
        price_chg = -price_chg

    pnl_usdt = round(position_usdt * price_chg, 2)
    pnl_pct  = round(pnl_usdt / capital * 100, 4)

    state["summary"]["current_capital"] = round(capital + pnl_usdt, 2)
    state["closed_trades"].append({
        "symbol":        pos["symbol"],
        "direction":     direction,
        "entry_time":    pos["entry_time"],
        "entry_price":   entry_price,
        "stop_price":    pos["stop_price"],
        "tp_price":      pos["tp_price"],
        "exit_time":     str(exit_time),
        "exit_reason":   exit_reason,
        "exit_price":    exit_price,
        "qty":           pos["qty"],
        "position_usdt": position_usdt,
        "leverage":      pos["leverage"],
        "pnl_usdt":      pnl_usdt,
        "pnl_pct":       pnl_pct,
    })
    _update_summary(state)
    log.info(
        f"[Paper] 平仓 {pos['symbol']} {direction} [{exit_reason}] "
        f"@ {exit_price:.2f}  PnL={pnl_pct:+.2f}%  ({pnl_usdt:+.1f}U)  "
        f"净值={state['summary']['current_capital']:.0f}U"
    )


# ── 外部接口 ─────────────────────────────────────────────────────────────────

def sync_to_state(signal_state: dict) -> None:
    """将 paper_trades summary 写入 signal_state 并确保 paper_trades.json 存在。"""
    pt = _load()
    _save(pt)
    signal_state["paper_trading"] = pt["summary"]
    maybe_generate_report()


def maybe_generate_report() -> None:
    """到达 END_DATE 后打印最终统计报告（幂等）。"""
    today = datetime.now(timezone.utc).date().isoformat()
    if today < END_DATE:
        return

    state  = _load()
    s      = state["summary"]
    closed = state["closed_trades"]

    log.info("=" * 55)
    log.info("[Paper Trading]  5 天模拟交易最终报告")
    log.info(f"  周期         : {s['start_date']}  →  {s['end_date']}")
    log.info(f"  总交易数     : {s['total_trades']}")
    if closed:
        pnls = [t["pnl_pct"] for t in closed]
        log.info(f"  胜率         : {s['win_rate']}%  ({s['win_trades']}胜 / {s['loss_trades']}负)")
        log.info(f"  总收益       : {s['total_pnl_pct']:+.2f}%  （净值 {s['current_capital']:.0f} U）")
        log.info(f"  最大单笔盈利 : {max(pnls):+.2f}%")
        log.info(f"  最大单笔亏损 : {min(pnls):+.2f}%")
    else:
        log.info("  无成交记录")
    log.info("=" * 55)
