"""
完整回测主脚本（STRATEGY.md 第一层：区间交易）

运行方式：
    python backtest.py

输出：
    - 控制台汇总表（版本 A vs 版本 B 并排）
    - equity_curve_15m_A.png / equity_curve_15m_B.png
    - equity_curve_1d_A.png  / equity_curve_1d_B.png
"""
from __future__ import annotations

import pandas as pd

from config import Config
from data.okx_feed import load_cache
from backtest.engine import Trade, run_backtest
from backtest.metrics import compute_stats, slice_period
from backtest.plot import plot_equity_curve

# ── 日期分割 ────────────────────────────────────────────────────────────────
# 15m 版（数据 2024-06-10 ~ 今）：前 18 个月调参，后 6 个月检验
SPLIT_15M = pd.Timestamp("2025-12-10", tz="UTC")
# 1d  版（数据 2020-01-01 ~ 今）：前 4.5 年调参，后 2 年检验
SPLIT_1D  = pd.Timestamp("2024-07-01", tz="UTC")

SYMBOLS       = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
INITIAL_EQ    = 10_000.0
BARS_15M_YEAR = 35_040   # 4 * 24 * 365
BARS_1D_YEAR  = 365

# ── 两个版本配置 ─────────────────────────────────────────────────────────────
VERSIONS: list[tuple[str, Config]] = [
    ("A-无限", Config()),                # 版本 A：无时间止损
    ("B-3天",  Config(max_hold_days=3)), # 版本 B：最多持仓 3 天
]


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def _label(sym: str) -> str:
    return sym.split("/")[0]   # "BTC/USDT:USDT" → "BTC"


def _combined_trades_equity(
    sym_results: dict[str, tuple[list[Trade], pd.Series]],
) -> tuple[list[Trade], pd.Series]:
    """将多个币种的交易和权益曲线合并（权益相加）。
    用 concat + sum 避免两条曲线长度差 1 根时产生 NaN。"""
    all_trades: list[Trade] = []
    curves: list[pd.Series] = []

    for trades, curve in sym_results.values():
        all_trades.extend(trades)
        curves.append(curve)

    all_trades.sort(key=lambda t: t.exit_time or pd.Timestamp.min)
    # ffill 填充长度不一致产生的 NaN，再按列求和
    eq_sum = pd.concat(curves, axis=1).ffill().bfill().sum(axis=1)
    return all_trades, eq_sum


def _print_table(rows: list[dict]) -> None:
    """打印汇总表格（含版本列）。"""
    cols   = ["周期", "币种", "版本", "段",
              "交易数", "胜率%", "期望值%", "盈亏比",
              "总收益%", "最大回撤%", "Sharpe"]
    widths = [6, 8, 8, 6, 6, 7, 8, 7, 8, 10, 7]

    def _fmt(row: dict) -> list[str]:
        s = row.get
        return [
            str(s("tf")),
            str(s("sym")),
            str(s("ver")),
            str(s("seg")),
            str(s("n_trades")),
            f"{s('win_rate'):.1f}",
            f"{s('expectancy_pct'):.3f}",
            f"{s('profit_factor'):.2f}",
            f"{s('total_return_pct'):.2f}",
            f"{s('max_drawdown_pct'):.2f}",
            f"{s('sharpe'):.2f}",
        ]

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    hdr = "|" + "|".join(f" {c:<{w}} " for c, w in zip(cols, widths)) + "|"

    print(sep)
    print(hdr)
    print(sep)
    last_group = None
    for row in rows:
        group = (row["tf"], row["sym"])
        if last_group is not None and group != last_group:
            print(sep)
        vals = _fmt(row)
        print("|" + "|".join(f" {v:<{w}} " for v, w in zip(vals, widths)) + "|")
        last_group = group
    print(sep)


# ── 15m 版回测（单个版本）────────────────────────────────────────────────────

def run_15m(ver_label: str, cfg: Config) -> list[dict]:
    print(f"\n  [15m {ver_label}] 运行中...")
    sym_results: dict[str, tuple[list[Trade], pd.Series]] = {}

    for sym in SYMBOLS:
        lbl  = _label(sym)
        h15m = load_cache(sym, "15m")
        h1   = load_cache(sym, "1h")
        trades, eq = run_backtest(sym, h15m, cfg, range_df=h1,
                                  initial_equity=INITIAL_EQ)
        sym_results[lbl] = (trades, eq)
        print(f"    {lbl}：{len(trades)} 笔成交")

    all_trades, all_eq = _combined_trades_equity(sym_results)

    curves = {lbl: eq for lbl, (_, eq) in sym_results.items()}
    plot_equity_curve(
        curves, SPLIT_15M,
        title=f"区间策略权益曲线（15m，{ver_label}，杠杆 5×）",
        save_path=f"equity_curve_15m_{ver_label[:1]}.png",
        initial_eq=INITIAL_EQ,
    )

    rows: list[dict] = []
    for lbl, (trades, eq) in sym_results.items():
        train_t, train_eq = slice_period(trades, eq, eq.index[0], SPLIT_15M)
        test_t,  test_eq  = slice_period(trades, eq, SPLIT_15M,
                                         eq.index[-1] + pd.Timedelta("1ns"))
        rows.append({"tf": "15m", "sym": lbl, "ver": ver_label,
                     "seg": "调参", **compute_stats(train_t, train_eq, BARS_15M_YEAR)})
        rows.append({"tf": "15m", "sym": lbl, "ver": ver_label,
                     "seg": "检验", **compute_stats(test_t,  test_eq,  BARS_15M_YEAR)})

    for seg in ("调参", "检验"):
        s_start = all_eq.index[0]  if seg == "调参" else SPLIT_15M
        s_end   = SPLIT_15M        if seg == "调参" else all_eq.index[-1] + pd.Timedelta("1ns")
        ct, ceq = slice_period(all_trades, all_eq, s_start, s_end)
        rows.append({"tf": "15m", "sym": "BTC+ETH", "ver": ver_label,
                     "seg": seg, **compute_stats(ct, ceq, BARS_15M_YEAR)})

    return rows


# ── 1d 版回测（单个版本）────────────────────────────────────────────────────

def run_1d(ver_label: str, cfg: Config) -> list[dict]:
    print(f"\n  [1d {ver_label}] 运行中...")
    sym_results: dict[str, tuple[list[Trade], pd.Series]] = {}

    for sym in SYMBOLS:
        lbl = _label(sym)
        h1d = load_cache(sym, "1d")
        trades, eq = run_backtest(sym, h1d, cfg, range_df=None,
                                  initial_equity=INITIAL_EQ)
        sym_results[lbl] = (trades, eq)
        print(f"    {lbl}：{len(trades)} 笔成交")

    all_trades, all_eq = _combined_trades_equity(sym_results)

    curves = {lbl: eq for lbl, (_, eq) in sym_results.items()}
    plot_equity_curve(
        curves, SPLIT_1D,
        title=f"区间策略权益曲线（1d，{ver_label}，杠杆 5×）",
        save_path=f"equity_curve_1d_{ver_label[:1]}.png",
        initial_eq=INITIAL_EQ,
    )

    rows: list[dict] = []
    for lbl, (trades, eq) in sym_results.items():
        train_t, train_eq = slice_period(trades, eq, eq.index[0], SPLIT_1D)
        test_t,  test_eq  = slice_period(trades, eq, SPLIT_1D,
                                         eq.index[-1] + pd.Timedelta("1ns"))
        rows.append({"tf": "1d", "sym": lbl, "ver": ver_label,
                     "seg": "调参", **compute_stats(train_t, train_eq, BARS_1D_YEAR)})
        rows.append({"tf": "1d", "sym": lbl, "ver": ver_label,
                     "seg": "检验", **compute_stats(test_t,  test_eq,  BARS_1D_YEAR)})

    for seg in ("调参", "检验"):
        s_start = all_eq.index[0] if seg == "调参" else SPLIT_1D
        s_end   = SPLIT_1D        if seg == "调参" else all_eq.index[-1] + pd.Timedelta("1ns")
        ct, ceq = slice_period(all_trades, all_eq, s_start, s_end)
        rows.append({"tf": "1d", "sym": "BTC+ETH", "ver": ver_label,
                     "seg": seg, **compute_stats(ct, ceq, BARS_1D_YEAR)})

    return rows


# ── 主入口 ───────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n成本：taker=0.05%  funding=0.01%/8h  slippage=0.01%/side  "
          "初始资金=10,000 USDT  杠杆上限=5×  单笔风险=1%")
    print(f"分割点：15m → {SPLIT_15M.date()}   1d → {SPLIT_1D.date()}")
    print("\n版本：")
    for label, cfg in VERSIONS:
        hold = "无限" if cfg.max_hold_days is None else f"{cfg.max_hold_days}天"
        print(f"  {label}：max_hold={hold}  N={cfg.N}  ADX阈值={cfg.adx_thresh}")

    print("\n" + "=" * 60)
    print("15m 版回测（entry=15m，range/ADX=1h）")
    print("=" * 60)
    rows_15m: list[dict] = []
    for ver_label, cfg in VERSIONS:
        rows_15m.extend(run_15m(ver_label, cfg))

    print("\n" + "=" * 60)
    print("1d 版回测（entry=1d，range/ADX=1d，N=48天窗口）")
    print("=" * 60)
    rows_1d: list[dict] = []
    for ver_label, cfg in VERSIONS:
        rows_1d.extend(run_1d(ver_label, cfg))

    # 按 (tf, sym, ver, seg) 排序，让同一币种的 A/B 版本相邻
    def _sort_key(r: dict) -> tuple:
        tf_ord  = {"15m": 0, "1d": 1}[r["tf"]]
        sym_ord = {"BTC": 0, "ETH": 1, "BTC+ETH": 2}.get(r["sym"], 9)
        ver_ord = 0 if "A" in r["ver"] else 1
        seg_ord = 0 if r["seg"] == "调参" else 1
        return (tf_ord, sym_ord, ver_ord, seg_ord)

    all_rows = sorted(rows_15m + rows_1d, key=_sort_key)

    print("\n" + "=" * 60)
    print("汇总对比表格（A=无时间止损，B=最多持仓3天）")
    print("=" * 60)
    _print_table(all_rows)


if __name__ == "__main__":
    main()
