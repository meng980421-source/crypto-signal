"""BTC 版本 F 基础上调参（调参段+检验段各 12 个月）
尝试三个方向：
  BTC-A：adx_thresh 收紧（20）—— 只在极度盘整时入场
  BTC-B：N 缩短（24）—— 1 天窗口，区间更紧
  BTC-C：A+B 叠加，同时收紧 ADX 和窗口
"""
from __future__ import annotations
import pandas as pd
from config import Config
from data.okx_feed import load_cache
from backtest.engine import run_backtest
from backtest.metrics import compute_stats, slice_period

SPLIT  = pd.Timestamp("2025-06-10", tz="UTC")
INITIAL = 10_000.0
BPY     = 35_040
BASE    = dict(tp_mode="opposite", chan_on=True, liuyao_on=True, chan_liuyao_and=True)

VERSIONS = [
    ("F-base",  Config(**BASE)),
    ("BTC-A",   Config(**BASE, adx_thresh=20.0)),
    ("BTC-B",   Config(**BASE, N=24)),
    ("BTC-C",   Config(**BASE, adx_thresh=20.0, N=24)),
]

h15m = load_cache("BTC/USDT:USDT", "15m")
h1   = load_cache("BTC/USDT:USDT", "1h")

rows = []
for ver, cfg in VERSIONS:
    trades, eq = run_backtest("BTC/USDT:USDT", h15m, cfg, range_df=h1, initial_equity=INITIAL)
    s_end = eq.index[-1] + pd.Timedelta("1ns")
    for seg, s, e in [("调参", eq.index[0], SPLIT), ("检验", SPLIT, s_end)]:
        t_sl, eq_sl = slice_period(trades, eq, s, e)
        rows.append({"ver": ver, "seg": seg, **compute_stats(t_sl, eq_sl, BPY)})

cols   = ["版本", "段", "交易数", "胜率%", "期望值%", "盈亏比", "总收益%", "最大回撤%", "Sharpe"]
widths = [9, 4, 5, 6, 7, 6, 7, 9, 6]
sep    = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
hdr    = "|" + "|".join(f" {c:<{w}} " for c, w in zip(cols, widths)) + "|"

print(f"\nBTC 调参（分割 {SPLIT.date()}，版本 F 基础参数 + 三种调整）")
print(sep); print(hdr); print(sep)
last_ver = None
for r in rows:
    if last_ver and r["ver"] != last_ver:
        print(sep)
    vals = [r["ver"], r["seg"], str(r["n_trades"]),
            f"{r['win_rate']:.1f}", f"{r['expectancy_pct']:.3f}",
            f"{r['profit_factor']:.2f}", f"{r['total_return_pct']:.2f}",
            f"{r['max_drawdown_pct']:.2f}", f"{r['sharpe']:.2f}"]
    print("|" + "|".join(f" {v:<{w}} " for v, w in zip(vals, widths)) + "|")
    last_ver = r["ver"]
print(sep)

best = [r for r in rows if r["seg"] == "检验"]
best.sort(key=lambda r: r["expectancy_pct"], reverse=True)
print(f"\n检验段期望值排序：")
for r in best:
    sign = "+" if r["expectancy_pct"] >= 0 else ""
    print(f"  {r['ver']}: {r['n_trades']}笔 期望值{sign}{r['expectancy_pct']:.3f}%")
