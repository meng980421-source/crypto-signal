"""
版本 F vs G 对比（15m，BTC+ETH 合并 + 分开，调参段+检验段各 12 个月）

版本 F：对侧止盈 + 缠论 AND 六爻（两层必须同向）
版本 G：对侧止盈 + 缠论 OR 六爻（任一放行；六爻观望不拦截）

调参段：2024-06-10 ~ 2025-06-10（前 12 个月）
检验段：2025-06-10 ~ 今         （后 12 个月）
"""
from __future__ import annotations
import pandas as pd
from config import Config
from data.okx_feed import load_cache
from backtest.engine import Trade, run_backtest
from backtest.metrics import compute_stats, slice_period

SPLIT      = pd.Timestamp("2025-06-10", tz="UTC")
SYMBOLS    = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
INITIAL    = 10_000.0
BPY        = 35_040

VERSIONS = [
    ("F",
     Config(tp_mode="opposite", chan_on=True, liuyao_on=True,
            chan_liuyao_and=True)),
    ("G",
     Config(tp_mode="opposite", chan_on=True, liuyao_on=True,
            chan_liuyao_and=False)),
]


def _lbl(sym: str) -> str:
    return sym.split("/")[0]


def _combined_eq(sym_results: dict) -> tuple[list[Trade], pd.Series]:
    all_trades: list[Trade] = []
    curves: list[pd.Series] = []
    for trades, eq in sym_results.values():
        all_trades.extend(trades)
        curves.append(eq)
    all_trades.sort(key=lambda t: t.exit_time or pd.Timestamp.min)
    eq_sum = pd.concat(curves, axis=1).ffill().bfill().sum(axis=1)
    return all_trades, eq_sum


def _print_table(rows: list[dict]) -> None:
    cols   = ["版本", "币种", "段", "交易数", "胜率%", "期望值%",
              "盈亏比", "总收益%", "最大回撤%", "Sharpe"]
    widths = [5, 10, 4, 5, 6, 7, 6, 7, 9, 6]

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    hdr = "|" + "|".join(f" {c:<{w}} " for c, w in zip(cols, widths)) + "|"

    print(sep); print(hdr); print(sep)
    last_block = None
    for r in rows:
        block = (r["ver"], r["sym"])
        if last_block and block != last_block:
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
        last_block = block
    print(sep)


# ── 主逻辑 ────────────────────────────────────────────────────────────────────
all_rows: list[dict] = []

for ver, cfg in VERSIONS:
    mode = "AND" if cfg.chan_liuyao_and else "OR"
    print(f"\n[{ver}] tp={cfg.tp_mode}  filter={mode}", flush=True)

    sym_results: dict[str, tuple[list[Trade], pd.Series]] = {}
    for sym in SYMBOLS:
        lbl  = _lbl(sym)
        h15m = load_cache(sym, "15m")
        h1   = load_cache(sym, "1h")
        trades, eq = run_backtest(sym, h15m, cfg, range_df=h1, initial_equity=INITIAL)
        sym_results[lbl] = (trades, eq)
        s_end = eq.index[-1] + pd.Timedelta("1ns")
        train_t, _ = slice_period(trades, eq, eq.index[0], SPLIT)
        test_t,  _ = slice_period(trades, eq, SPLIT, s_end)
        print(f"  {lbl}: 总{len(trades)}笔  调参{len(train_t)} / 检验{len(test_t)}")

    # 合并 BTC+ETH
    comb_trades, comb_eq = _combined_eq(sym_results)
    comb_end = comb_eq.index[-1] + pd.Timedelta("1ns")

    # 统计：BTC、ETH、合并 × 调参/检验
    for lbl, (trades, eq) in sym_results.items():
        s_end = eq.index[-1] + pd.Timedelta("1ns")
        for seg, (s, e) in [("调参", (eq.index[0], SPLIT)),
                             ("检验", (SPLIT, s_end))]:
            t_sl, eq_sl = slice_period(trades, eq, s, e)
            all_rows.append({"ver": ver, "sym": lbl, "seg": seg,
                             **compute_stats(t_sl, eq_sl, BPY)})

    for seg, (s, e) in [("调参", (comb_eq.index[0], SPLIT)),
                         ("检验", (SPLIT, comb_end))]:
        t_sl, eq_sl = slice_period(comb_trades, comb_eq, s, e)
        all_rows.append({"ver": ver, "sym": "BTC+ETH", "seg": seg,
                         **compute_stats(t_sl, eq_sl, BPY)})
    print(f"  合并: 调参{sum(1 for r in all_rows if r['ver']==ver and r['sym']=='BTC+ETH' and r['seg']=='调参' for _ in [r])} 行")

# ── 排序：版本 → 币种（BTC / ETH / BTC+ETH）→ 段 ─────────────────────────────
_SYM = {"BTC": 0, "ETH": 1, "BTC+ETH": 2}
_VER = {"F": 0, "G": 1}
_SEG = {"调参": 0, "检验": 1}
all_rows.sort(key=lambda r: (_VER.get(r["ver"], 9),
                              _SYM.get(r["sym"],  9),
                              _SEG.get(r["seg"],  9)))

print(f"\n{'='*70}")
print(f"15m 版本 F vs G（调参 2024-06-10~2025-06-10，检验 2025-06-10~今）")
print(f"{'='*70}")
_print_table(all_rows)
print("\nF=AND(缠论必须+六爻必须)  G=OR(任一放行+六爻观望不拦截)")

# ── 汇总检验段信号数（重点关注 BTC+ETH combined）──────────────────────────────
print("\n── 检验段 BTC+ETH 合并汇总 ──")
for r in all_rows:
    if r["sym"] == "BTC+ETH" and r["seg"] == "检验":
        sign = "+" if r["expectancy_pct"] >= 0 else ""
        print(f"  {r['ver']}: {r['n_trades']}笔  期望值{sign}{r['expectancy_pct']:.3f}%  "
              f"总收益{sign}{r['total_return_pct']:.2f}%  Sharpe={r['sharpe']:.2f}")
