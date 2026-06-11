"""
15m 四版本对比（A / D / E / F）
BTC 和 ETH 分开输出，调参段 + 检验段
"""
from __future__ import annotations
import pandas as pd
from config import Config
from data.okx_feed import load_cache
from backtest.engine import run_backtest
from backtest.metrics import compute_stats, slice_period

SPLIT_15M = pd.Timestamp("2025-12-10", tz="UTC")
SYMBOLS   = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
INITIAL   = 10_000.0
BPY       = 35_040

# ── 四版本定义 ────────────────────────────────────────────────────────────────
VERSIONS = [
    ("A",
     Config()),                                         # 基准：中线止盈，无过滤
    ("D",
     Config(tp_mode="opposite")),                       # 改止盈：对侧边沿
    ("E",
     Config(chan_on=True, liuyao_on=True)),              # 中线止盈 + 缠论 + 六爻
    ("F",
     Config(tp_mode="opposite", chan_on=True,
            liuyao_on=True)),                            # 对侧止盈 + 缠论 + 六爻
]


def _lbl(sym: str) -> str:
    return sym.split("/")[0]


def _print_table(rows: list[dict]) -> None:
    cols   = ["版本", "币种", "段", "交易数", "胜率%", "期望值%",
              "盈亏比", "总收益%", "最大回撤%", "Sharpe"]
    widths = [5, 4, 4, 5, 6, 7, 6, 7, 9, 6]

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    hdr = "|" + "|".join(f" {c:<{w}} " for c, w in zip(cols, widths)) + "|"

    print(sep); print(hdr); print(sep)
    last_sym = None
    for r in rows:
        if last_sym and r["sym"] != last_sym:
            print(sep)
        vals = [
            r["ver"], r["sym"], r["seg"],
            str(r["n_trades"]),
            f"{r['win_rate']:.1f}",
            f"{r['expectancy_pct']:.3f}",
            f"{r['profit_factor']:.2f}",
            f"{r['total_return_pct']:.2f}",
            f"{r['max_drawdown_pct']:.2f}",
            f"{r['sharpe']:.2f}",
        ]
        print("|" + "|".join(f" {v:<{w}} " for v, w in zip(vals, widths)) + "|")
        last_sym = r["sym"]
    print(sep)


# ── 主逻辑 ────────────────────────────────────────────────────────────────────
all_rows: list[dict] = []

for ver, cfg in VERSIONS:
    print(f"\n[{ver}] chan={cfg.chan_on} liuyao={cfg.liuyao_on} tp={cfg.tp_mode}")
    for sym in SYMBOLS:
        lbl  = _lbl(sym)
        h15m = load_cache(sym, "15m")
        h1   = load_cache(sym, "1h")
        trades, eq = run_backtest(sym, h15m, cfg, range_df=h1, initial_equity=INITIAL)
        s_end = eq.index[-1] + pd.Timedelta("1ns")

        train_t, train_eq = slice_period(trades, eq, eq.index[0], SPLIT_15M)
        test_t,  test_eq  = slice_period(trades, eq, SPLIT_15M,   s_end)

        all_rows.append({"ver": ver, "sym": lbl, "seg": "调参",
                         **compute_stats(train_t, train_eq, BPY)})
        all_rows.append({"ver": ver, "sym": lbl, "seg": "检验",
                         **compute_stats(test_t,  test_eq,  BPY)})

        print(f"  {lbl}: 总{len(trades)}笔  "
              f"调参{len(train_t)}笔 / 检验{len(test_t)}笔")

# ── 排序：先按 sym，再按 ver，再按 seg ────────────────────────────────────────
_SYM_ORD = {"BTC": 0, "ETH": 1}
_VER_ORD  = {"A": 0, "D": 1, "E": 2, "F": 3}
_SEG_ORD  = {"调参": 0, "检验": 1}
all_rows.sort(key=lambda r: (
    _SYM_ORD.get(r["sym"], 9),
    _VER_ORD.get(r["ver"], 9),
    _SEG_ORD.get(r["seg"], 9),
))

print(f"\n{'='*65}")
print(f"15m 四版本对比（分割点：{SPLIT_15M.date()}，调参段+检验段）")
print(f"{'='*65}")
_print_table(all_rows)
print("\n说明：A=基准  D=对侧止盈  E=中线+缠论+六爻  F=对侧+缠论+六爻")
