"""ETH 版本 F 检验段完整明细"""
from __future__ import annotations
import pandas as pd
from config import Config
from data.okx_feed import load_cache
from backtest.engine import run_backtest
from backtest.metrics import compute_stats, slice_period

SPLIT  = pd.Timestamp("2025-06-10", tz="UTC")
INITIAL = 10_000.0
BPY     = 35_040

cfg = Config(tp_mode="opposite", chan_on=True, liuyao_on=True, chan_liuyao_and=True)

h15m = load_cache("ETH/USDT:USDT", "15m")
h1   = load_cache("ETH/USDT:USDT", "1h")
trades, eq = run_backtest("ETH/USDT:USDT", h15m, cfg, range_df=h1, initial_equity=INITIAL)

s_end = eq.index[-1] + pd.Timedelta("1ns")
test_t, test_eq = slice_period(trades, eq, SPLIT, s_end)
s = compute_stats(test_t, test_eq, BPY)

print(f"\nETH 版本 F 检验段（{SPLIT.date()} ~ {eq.index[-1].date()}）")
print(f"交易数={s['n_trades']}  胜率={s['win_rate']:.1f}%  "
      f"期望值={s['expectancy_pct']:+.3f}%  盈亏比={s['profit_factor']:.2f}")
print(f"总收益={s['total_return_pct']:+.2f}%  最大回撤={s['max_drawdown_pct']:.2f}%  "
      f"Sharpe={s['sharpe']:.2f}")

print(f"\n{'─'*105}")
hdr = f"{'入场时间':<22} {'方向':<6} {'入场价':>9} {'止损价':>9} {'止盈价':>9} "
hdr += f"{'出场时间':<22} {'出场原因':<6} {'盈亏%':>8} {'持仓时长':>12}"
print(hdr)
print('─'*105)

for t in sorted(test_t, key=lambda x: x.entry_time):
    dur = t.exit_time - t.entry_time
    hours = int(dur.total_seconds() // 3600)
    mins  = int((dur.total_seconds() % 3600) // 60)
    dur_str = f"{hours}h{mins:02d}m"
    reason_map = {"sl": "止损", "tp": "止盈", "time": "时间"}
    reason = reason_map.get(t.exit_reason, t.exit_reason)
    sign = "+" if t.pnl_pct >= 0 else ""
    print(
        f"{str(t.entry_time)[:19]:<22} "
        f"{'多' if t.direction=='long' else '空':<6} "
        f"{t.entry_price:>9.2f} "
        f"{t.stop_price:>9.2f} "
        f"{t.tp_price:>9.2f} "
        f"{str(t.exit_time)[:19]:<22} "
        f"{reason:<6} "
        f"{sign}{t.pnl_pct:>7.2f}% "
        f"{dur_str:>12}"
    )
print('─'*105)
