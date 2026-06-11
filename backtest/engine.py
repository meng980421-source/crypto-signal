"""
回测引擎：逐 K 线模拟持仓，计算净 PnL（含手续费、资金费、滑点）。

两种模式
  15m 模式：entry_df=h15m，range_df=h1（1h 算区间和 ADX）
  1d  模式：entry_df=h1d，range_df=None（同一 df 既做区间又做入场触发）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from config import Config
from indicators import adx as calc_adx
from strategy.chan import compute_chan_signals
from strategy.liuyao import compute_liuyao_series

# ── 成本常量 ───────────────────────────────────────────────────────────────
TAKER_FEE   = 0.0005   # 0.05% taker 手续费
FUNDING_8H  = 0.0001   # 0.01% per 8h 资金费（多空均按成本计）
SLIPPAGE    = 0.0001   # 0.01% 单边滑点（≈ 1-2 个最小跳动）


@dataclass
class Trade:
    symbol:          str
    direction:       str            # "long" | "short"
    entry_time:      pd.Timestamp
    entry_price:     float
    stop_price:      float
    tp_price:        float
    size:            float          # 持仓张数（资产单位，BTC / ETH）
    equity_at_entry: float
    leverage:        float

    exit_time:   Optional[pd.Timestamp] = None
    exit_price:  Optional[float]        = None
    exit_reason: Optional[str]          = None   # "sl" | "tp" | "time"
    pnl_net:     Optional[float]        = None   # 净盈亏（USDT）
    pnl_pct:     Optional[float]        = None   # 净盈亏占入场权益的百分比


def _size_and_lev(equity: float, risk_pct: float, entry: float,
                  stop: float, max_lev: float) -> tuple[float, float]:
    """返回 (size, leverage)，杠杆上限为 max_lev。"""
    stop_dist = abs(entry - stop)
    if stop_dist < 1e-9:
        return 0.0, 0.0
    size      = equity * risk_pct / stop_dist
    notional  = size * entry
    lev       = notional / equity
    if lev > max_lev:
        lev  = max_lev
        size = equity * max_lev / entry
    return size, lev


def run_backtest(
    symbol:          str,
    entry_df:        pd.DataFrame,
    cfg:             Config,
    range_df:        Optional[pd.DataFrame] = None,
    initial_equity:  float = 10_000.0,
) -> tuple[list[Trade], pd.Series]:
    """
    逐 K 线回放，返回 (trades, equity_curve)。

    Parameters
    ----------
    symbol     : 币种名称
    entry_df   : 入场触发周期的 K 线（15m 或 1d）
    cfg        : 策略参数
    range_df   : 区间 / ADX 计算周期的 K 线（1h）；None 表示与 entry_df 相同（1d 模式）
    initial_equity : 初始权益（USDT）

    Returns
    -------
    trades       : 已平仓的 Trade 列表，含完整盈亏信息
    equity_curve : pd.Series，每根 K 线末的逐日盯市权益
    """
    _rdf      = range_df if range_df is not None else entry_df
    sep_range = range_df is not None   # True = 15m+1h 模式

    # ── 预计算（向量化，只算一次）─────────────────────────────────────────
    adx_s        = calc_adx(_rdf, cfg.adx_len)
    roll_upper   = _rdf["high"].rolling(cfg.N).max()
    roll_lower   = _rdf["low"].rolling(cfg.N).min()
    roll_mid     = (roll_upper + roll_lower) / 2.0

    # 缠论：在 range_df（1h）上预计算背驰信号
    chan_s = compute_chan_signals(_rdf) if cfg.chan_on else None
    # 六爻：在 entry_df（15m）上预计算方向偏向
    liuyao_s = compute_liuyao_series(entry_df) if cfg.liuyao_on else None

    max_hold = (pd.Timedelta(days=cfg.max_hold_days)
                if cfg.max_hold_days is not None else None)

    realized_eq: float = initial_equity
    open_pos: dict[str, Optional[dict]] = {"long": None, "short": None}

    eq_idx: list[pd.Timestamp] = []
    eq_val: list[float]        = []
    trades: list[Trade]        = []

    for ts, row in entry_df.iterrows():
        close = float(row["close"])

        # ── 盯市权益（含未平仓浮盈浮亏）──────────────────────────────────
        mtm = realized_eq
        for direction, pos in open_pos.items():
            if pos is None:
                continue
            t: Trade = pos["trade"]
            raw_unreal = ((close - t.entry_price) if direction == "long"
                          else (t.entry_price - close)) * t.size
            hold_h   = (ts - t.entry_time).total_seconds() / 3600
            fund_now = (hold_h / 8) * FUNDING_8H * t.size * t.entry_price
            mtm     += raw_unreal - fund_now
        eq_idx.append(ts)
        eq_val.append(mtm)

        # ── 检查出场（止盈 / 止损 / 时间止损）────────────────────────────
        for direction in ("long", "short"):
            pos = open_pos[direction]
            if pos is None:
                continue
            t = pos["trade"]
            elapsed = ts - t.entry_time

            hit_sl   = (direction == "long"  and close <  t.stop_price) or \
                       (direction == "short" and close >  t.stop_price)
            hit_tp   = (direction == "long"  and close >= t.tp_price)   or \
                       (direction == "short" and close <= t.tp_price)
            hit_time = max_hold is not None and elapsed >= max_hold

            if not (hit_sl or hit_tp or hit_time):
                continue

            exit_px = (t.stop_price if hit_sl else
                       t.tp_price   if hit_tp else close)
            reason  = "sl" if hit_sl else "tp" if hit_tp else "time"

            notional    = t.size * t.entry_price
            raw_pnl     = ((exit_px - t.entry_price) if direction == "long"
                           else (t.entry_price - exit_px)) * t.size
            entry_cost  = notional         * (TAKER_FEE + SLIPPAGE)
            exit_cost   = t.size * exit_px * (TAKER_FEE + SLIPPAGE)
            hold_h      = elapsed.total_seconds() / 3600
            funding     = (hold_h / 8) * FUNDING_8H * notional
            net_pnl     = raw_pnl - entry_cost - exit_cost - funding

            realized_eq      += net_pnl
            t.exit_time       = ts
            t.exit_price      = exit_px
            t.exit_reason     = reason
            t.pnl_net         = net_pnl
            t.pnl_pct         = net_pnl / t.equity_at_entry * 100.0
            trades.append(t)
            open_pos[direction] = None

        # ── 查找当前区间和 ADX ────────────────────────────────────────────
        # sep_range=True(15m+1h): 用"刚收盘的最后一根 1h 棒"
        # sep_range=False(1d): 直接用当前 1d 棒（已收盘）
        lrt = (ts.floor("1h") - pd.Timedelta("1h")) if sep_range else ts

        upper = roll_upper.asof(lrt)
        lower = roll_lower.asof(lrt)
        mid   = roll_mid.asof(lrt)
        adx_v = adx_s.asof(lrt)

        if pd.isna(upper) or pd.isna(lower):
            continue
        if not pd.isna(adx_v) and adx_v >= cfg.adx_thresh:
            continue

        # ── 缠论/六爻预查 ────────────────────────────────────────────────
        chan_v    = chan_s.asof(lrt)       if chan_s    is not None else "none"
        liuyao_v  = liuyao_s.at[ts]       if liuyao_s is not None else "neutral"

        # ── 过滤器：_passes(dir) → 是否允许入场 ─────────────────────────
        def _passes(need_chan: str, need_liuyao: str) -> bool:
            both_on = cfg.chan_on and cfg.liuyao_on
            if both_on and cfg.chan_liuyao_and:
                # AND 模式：两层必须同向（版本 F）
                return chan_v == need_chan and liuyao_v == need_liuyao
            if both_on and not cfg.chan_liuyao_and:
                # OR 模式：任一放行即可；六爻观望不拦截（版本 G）
                # 只有六爻反向（bear/bull 相反）且缠论也不支持时才拦截
                liuyao_ok  = liuyao_v in (need_liuyao, "neutral")
                return chan_v == need_chan or liuyao_ok
            if cfg.chan_on:
                return chan_v == need_chan
            if cfg.liuyao_on:
                return liuyao_v == need_liuyao
            return True

        # ── 入场条件 ──────────────────────────────────────────────────────
        if open_pos["long"] is None and close <= lower * (1 + cfg.edge_buffer):
            stop = lower * (1 - cfg.stop_buffer)
            tp   = mid if cfg.tp_mode == "mid" else upper
            if close > stop and _passes("bull", "bull"):
                sz, lev = _size_and_lev(realized_eq, cfg.risk_per_trade,
                                        close, stop, cfg.max_leverage)
                if sz > 0:
                    t = Trade(symbol, "long", ts, close, stop, tp,
                              sz, realized_eq, lev)
                    open_pos["long"] = {"trade": t}

        if open_pos["short"] is None and close >= upper * (1 - cfg.edge_buffer):
            stop = upper * (1 + cfg.stop_buffer)
            tp   = mid if cfg.tp_mode == "mid" else lower
            if close < stop and _passes("bear", "bear"):
                sz, lev = _size_and_lev(realized_eq, cfg.risk_per_trade,
                                        close, stop, cfg.max_leverage)
                if sz > 0:
                    t = Trade(symbol, "short", ts, close, stop, tp,
                              sz, realized_eq, lev)
                    open_pos["short"] = {"trade": t}

    equity_curve = pd.Series(eq_val, index=pd.DatetimeIndex(eq_idx), name="equity")
    return trades, equity_curve
