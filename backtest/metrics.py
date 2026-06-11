"""
回测统计指标计算。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest.engine import Trade


def compute_stats(
    trades: list[Trade],
    equity_curve: pd.Series,
    bars_per_year: int = 35_040,    # 15m: 4*24*365; 1d: 365
) -> dict:
    """
    返回统计字典：
      n_trades, win_rate(%), expectancy_pct(%), profit_factor,
      total_return_pct(%), max_drawdown_pct(%), sharpe
    """
    empty = dict(n_trades=0, win_rate=0.0, expectancy_pct=0.0,
                 profit_factor=0.0, total_return_pct=0.0,
                 max_drawdown_pct=0.0, sharpe=0.0)

    if not trades or len(equity_curve) < 2:
        return empty

    pnl_net  = np.array([t.pnl_net  for t in trades], dtype=float)
    pnl_pct  = np.array([t.pnl_pct  for t in trades], dtype=float)

    wins   = pnl_net[pnl_net > 0]
    losses = pnl_net[pnl_net <= 0]

    win_rate    = len(wins) / len(pnl_net) * 100.0
    expectancy  = float(np.mean(pnl_pct))            # 每笔期望收益（占权益%）
    avg_win     = float(np.mean(wins))   if len(wins)   else 0.0
    avg_loss    = float(np.mean(losses)) if len(losses) else 0.0
    pf          = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

    init_eq   = float(equity_curve.iloc[0])
    final_eq  = float(equity_curve.iloc[-1])
    total_ret = (final_eq - init_eq) / init_eq * 100.0

    # 最大回撤（百分比，负数）
    running_max = equity_curve.cummax()
    drawdown    = (equity_curve - running_max) / running_max
    max_dd      = float(drawdown.min()) * 100.0

    # Sharpe（年化）
    bar_rets = equity_curve.pct_change().dropna()
    if len(bar_rets) > 1 and bar_rets.std() > 1e-12:
        sharpe = bar_rets.mean() / bar_rets.std() * np.sqrt(bars_per_year)
    else:
        sharpe = 0.0

    return dict(
        n_trades         = int(len(pnl_net)),
        win_rate         = round(win_rate, 1),
        expectancy_pct   = round(expectancy, 3),
        profit_factor    = round(pf, 2),
        total_return_pct = round(total_ret, 2),
        max_drawdown_pct = round(max_dd, 2),
        sharpe           = round(sharpe, 2),
    )


def slice_period(
    trades: list[Trade],
    equity_curve: pd.Series,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[list[Trade], pd.Series]:
    """按时间切片交易列表和权益曲线（左闭右开）。"""
    sliced_trades = [
        t for t in trades
        if t.exit_time is not None and start <= t.exit_time < end
    ]
    sliced_equity = equity_curve.loc[start:end]
    return sliced_trades, sliced_equity
