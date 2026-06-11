"""
第一层：区间交易信号逻辑（STRATEGY.md §2）
- 区间识别：1h 回看 N 根，上沿/下沿/中线
- 震荡过滤：1h ADX(14) < 25
- 入场触发：15m 收盘贴近边沿
- 出场：止盈=中线，止损=边沿突破，时间止损=5天
- 同币种同方向同时最多 1 仓
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from config import Config
from indicators import adx as calc_adx


@dataclass
class Signal:
    timestamp: pd.Timestamp
    symbol: str
    direction: Literal["long", "short"]
    entry_price: float
    stop_price: float
    tp_price: float

    def __str__(self) -> str:
        arrow = "▲ 做多" if self.direction == "long" else "▼ 做空"
        return (
            f"{self.timestamp}  {self.symbol}  {arrow}"
            f"  入场={self.entry_price:,.2f}"
            f"  止损={self.stop_price:,.2f}"
            f"  止盈={self.tp_price:,.2f}"
        )


def _range_at(h1_slice: pd.DataFrame, N: int) -> tuple[float, float, float]:
    """从 1h 切片末尾取 N 根，返回 (upper, lower, mid)。"""
    window = h1_slice.iloc[-N:]
    upper = float(window["high"].max())
    lower = float(window["low"].min())
    mid = (upper + lower) / 2.0
    return upper, lower, mid


def run_signals(
    symbol: str,
    h15m: pd.DataFrame,
    h1: pd.DataFrame,
    cfg: Config | None = None,
) -> list[Signal]:
    """
    在给定历史数据上回放，返回所有入场 Signal 列表（按时间顺序）。

    Parameters
    ----------
    symbol : 币种标识，写入 Signal.symbol
    h15m   : 15m K 线 DataFrame（index=UTC Timestamp）
    h1     : 1h K 线 DataFrame（index=UTC Timestamp）
    cfg    : 参数，默认使用 Config()
    """
    if cfg is None:
        cfg = Config()

    # 预计算整条 1h ADX 序列（只算一次）
    h1_adx: pd.Series = calc_adx(h1, cfg.adx_len)

    signals: list[Signal] = []
    max_hold = (pd.Timedelta(days=cfg.max_hold_days)
                if cfg.max_hold_days is not None else None)

    # 持仓状态：None 表示空仓
    open_pos: dict[str, dict | None] = {"long": None, "short": None}

    for ts, row in h15m.iterrows():
        close = float(row["close"])

        # ── 1. 检查持仓出场（无论 ADX 状态都要检查）────────────────────
        for direction in ("long", "short"):
            pos = open_pos[direction]
            if pos is None:
                continue
            sig: Signal = pos["signal"]
            elapsed = ts - pos["open_ts"]

            if direction == "long":
                hit_sl = close < sig.stop_price
                hit_tp = close >= sig.tp_price
            else:
                hit_sl = close > sig.stop_price
                hit_tp = close <= sig.tp_price

            hit_time = max_hold is not None and elapsed >= max_hold
            if hit_sl or hit_tp or hit_time:
                open_pos[direction] = None

        # ── 2. 计算当前 1h 区间和 ADX ──────────────────────────────────
        # 用"刚刚收盘的最后一根 1h K 线"：floor 到小时后再退一格
        last_1h_ts = ts.floor("1h") - pd.Timedelta("1h")

        # 取到该时刻为止的所有 1h 数据
        h1_slice = h1.loc[h1.index <= last_1h_ts]
        if len(h1_slice) < cfg.N:
            continue  # 历史不足以构建区间

        # ADX：用 asof 找 <= last_1h_ts 的最新值
        adx_val = h1_adx.asof(last_1h_ts)
        # ADX 为 NaN 时（热身期或零振幅横盘），视为"无趋势"，允许入场

        # ── 3. 震荡过滤（ADX 有值且 >= 阈值才视为趋势，跳过入场）────────
        if not pd.isna(adx_val) and adx_val >= cfg.adx_thresh:
            continue

        upper, lower, mid = _range_at(h1_slice, cfg.N)

        # ── 4. 入场条件（15m 收盘触发）──────────────────────────────────
        # 做多：收盘贴近下沿；止损必须在入场价下方，否则价格已破位，跳过
        if open_pos["long"] is None and close <= lower * (1 + cfg.edge_buffer):
            stop = lower * (1 - cfg.stop_buffer)
            tp = mid if cfg.tp_mode == "mid" else upper
            if close > stop:  # 合理性校验
                sig = Signal(ts, symbol, "long", close, stop, tp)
                open_pos["long"] = {"signal": sig, "open_ts": ts}
                signals.append(sig)

        # 做空：收盘贴近上沿；止损必须在入场价上方，否则价格已破位，跳过
        if open_pos["short"] is None and close >= upper * (1 - cfg.edge_buffer):
            stop = upper * (1 + cfg.stop_buffer)
            tp = mid if cfg.tp_mode == "mid" else lower
            if close < stop:  # 合理性校验
                sig = Signal(ts, symbol, "short", close, stop, tp)
                open_pos["short"] = {"signal": sig, "open_ts": ts}
                signals.append(sig)

    return signals
