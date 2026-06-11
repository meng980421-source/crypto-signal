"""
定时调度器：每 15 分钟拉最新 K 线、跑信号、有新信号就推送

运行模式：
    python scheduler.py           # 持续运行（本地 / Railway）
    python scheduler.py --once    # 单次执行（GitHub Actions cron）

状态持久化到 signal_state.json（按 last_bar 去重，杜绝重复推送）。
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import schedule
import pandas as pd
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from config import BTC_LIVE, ETH_LIVE
from data.okx_feed import refresh_cache, load_cache
from notifier.fcm import notify_entry, notify_exit
import paper_trading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── 生产配置（BTC-B + ETH-F） ─────────────────────────────────────────────────
CONFIGS = {
    "BTC/USDT:USDT": BTC_LIVE,
    "ETH/USDT:USDT": ETH_LIVE,
}

STATE_FILE = Path(__file__).parent / "signal_state.json"

# 每个币种运行回测所用的回看窗口（15m K 线根数）
# 需要覆盖 max(N)*几倍 + ADX 预热 + 缠论预热
_WINDOW = 500


# ── 状态管理 ──────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, default=str, indent=2, ensure_ascii=False))


_HISTORY_MAX = 50


def _sym_state(state: dict, symbol: str) -> dict:
    return state.setdefault(symbol, {
        "last_bar":   None,   # 最后处理过的 15m bar timestamp（ISO 字符串）
        "open_long":  None,   # {"entry_time", "entry_price", "stop_price", "tp_price"}
        "open_short": None,
    })


def _append_history(state: dict, record: dict) -> None:
    history = state.setdefault("history", [])
    history.append(record)
    if len(history) > _HISTORY_MAX:
        state["history"] = history[-_HISTORY_MAX:]


# ── 核心逻辑 ──────────────────────────────────────────────────────────────────

def _run_signals_for(symbol: str, state: dict) -> None:
    from backtest.engine import run_backtest

    cfg = CONFIGS[symbol]
    lbl = symbol.split("/")[0]

    # 1. 刷新行情
    try:
        refresh_cache([symbol], ["15m", "1h"])
    except Exception as exc:
        log.warning(f"{lbl}: 行情刷新失败 ({exc})")
        return

    h15m = load_cache(symbol, "15m")
    h1   = load_cache(symbol, "1h")

    current_bar = h15m.index[-1]   # 最新已收盘的 15m bar

    # 2. 检查是否有新 bar
    ss = _sym_state(state, symbol)
    last_bar_str = ss["last_bar"]
    last_bar = pd.Timestamp(last_bar_str, tz="UTC") if last_bar_str else None

    if last_bar is not None and current_bar <= last_bar:
        log.info(f"{lbl}: 无新 bar（last={last_bar.strftime('%H:%M')}），跳过")
        return

    # 3. 确定需要检测的 bar 范围
    #    首次运行：只通知第一次，不回溯历史
    if last_bar is None:
        check_since = current_bar   # 仅处理最新 bar
        log.info(f"{lbl}: 首次运行，初始化状态")
    else:
        check_since = last_bar + pd.Timedelta(minutes=1)

    # Paper trading: 用本 bar 收盘价检查已有持仓
    current_price = float(h15m.iloc[-1]["close"])
    paper_trading.check_positions(symbol, current_price, current_bar.to_pydatetime())

    # 4. 跑回测（窗口内），提取新 bar 产生的信号
    recent   = h15m.tail(_WINDOW)
    h1_slice = h1[h1.index >= recent.index[0] - pd.Timedelta(hours=50)]
    trades, _ = run_backtest(symbol, recent, cfg,
                             range_df=h1_slice, initial_equity=10_000.0)

    # 5. 筛选新入场 / 新离场
    new_entries = [t for t in trades if t.entry_time >= check_since]
    new_exits   = [t for t in trades
                   if t.exit_time is not None and t.exit_time >= check_since]

    # 6. 推送 & 更新状态
    for t in sorted(new_entries, key=lambda x: x.entry_time):
        key = f"open_{t.direction}"
        if ss.get(key) is None:          # 避免重复开仓推送
            log.info(f"{lbl}: 入场 {t.direction} @ {t.entry_price:.2f}  "
                     f"SL={t.stop_price:.2f}  TP={t.tp_price:.2f}")
            notify_entry(symbol, t.direction,
                         t.entry_price, t.stop_price, t.tp_price)
            ss[key] = {
                "entry_time":  str(t.entry_time),
                "entry_price": t.entry_price,
                "stop_price":  t.stop_price,
                "tp_price":    t.tp_price,
            }
            paper_trading.open_position(
                symbol, t.direction,
                t.entry_price, t.stop_price, t.tp_price,
                str(t.entry_time),
            )

    for t in sorted(new_exits, key=lambda x: x.exit_time):
        key = f"open_{t.direction}"
        if ss.get(key) is not None:      # 只有已记录的持仓才推送平仓
            log.info(f"{lbl}: 离场 {t.direction} [{t.exit_reason}] "
                     f"{t.pnl_pct:+.2f}%")
            notify_exit(symbol, t.direction, t.exit_reason, t.pnl_pct)
            _append_history(state, {
                "symbol":      lbl,
                "direction":   t.direction,
                "entry_time":  str(ss[key]["entry_time"]),
                "entry_price": ss[key]["entry_price"],
                "stop_price":  ss[key]["stop_price"],
                "tp_price":    ss[key]["tp_price"],
                "exit_time":   str(t.exit_time),
                "exit_reason": t.exit_reason,
                "pnl_pct":     round(t.pnl_pct, 4),
            })
            ss[key] = None

    ss["last_bar"] = str(current_bar)
    log.info(f"{lbl}: OK  bar={current_bar.strftime('%Y-%m-%d %H:%M')}  "
             f"新入场={len(new_entries)}  新离场={len(new_exits)}")


def job() -> None:
    log.info("──────── 信号检测开始 ────────")
    state = _load_state()
    for symbol in CONFIGS:
        _run_signals_for(symbol, state)
    paper_trading.sync_to_state(state)
    _save_state(state)
    log.info("──────── 信号检测完成 ────────")


# ── 入口 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--once" in sys.argv:
        # GitHub Actions 单次模式
        log.info("单次运行模式（--once）")
        job()
    else:
        # 本地 / Railway 持续运行模式
        log.info("调度器启动（每 15 分钟）")
        job()   # 启动时立即执行一次
        schedule.every(15).minutes.do(job)
        while True:
            schedule.run_pending()
            time.sleep(30)
