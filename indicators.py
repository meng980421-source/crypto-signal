"""
技术指标库。
ADX 使用 Wilder RMA（alpha=1/period，seed=首N根均值），与 TradingView 一致，
确保 ADX 值域 [0, 100]。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _wilder_smooth(arr: np.ndarray, period: int) -> np.ndarray:
    """
    Wilder 平滑（种子=首 period 根之和）。
    S_n = S_{n-1} - S_{n-1}/period + arr[n]
    用于 TR / +DM / -DM 的中间计算；稳态值 = period × 平均值（比值时 N 约掉）。
    对外暴露仅供单元测试验证数学正确性。
    """
    out = np.full(len(arr), np.nan)
    start = 0
    while start < len(arr) and np.isnan(arr[start]):
        start += 1
    if start + period > len(arr):
        return out
    out[start + period - 1] = arr[start : start + period].sum()
    for i in range(start + period, len(arr)):
        out[i] = out[i - 1] - out[i - 1] / period + arr[i]
    return out


def _rma(arr: np.ndarray, period: int) -> np.ndarray:
    """
    Wilder RMA（alpha=1/period，种子=首 period 根均值）。
    S_n = S_{n-1} × (period-1)/period + arr[n] / period
    稳态值 = 输入均值，与输入同量纲；用于 DX→ADX 保证值域 [0,100]。
    """
    out = np.full(len(arr), np.nan)
    start = 0
    while start < len(arr) and np.isnan(arr[start]):
        start += 1
    if start + period > len(arr):
        return out
    window = arr[start : start + period]
    if np.all(np.isnan(window)):
        return out
    out[start + period - 1] = np.nanmean(window)
    alpha = 1.0 / period
    for i in range(start + period, len(arr)):
        out[i] = out[i - 1] * (1.0 - alpha) + arr[i] * alpha
    return out


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Wilder ADX(period)。
    TR / +DM / -DM 用 _wilder_smooth（N 在 DI 比值时约掉，结果不变）；
    DX → ADX 用 _rma 保证值域 [0, 100]。
    输入 df 须含 high / low / close 列，index 为时间序列。
    前 2*period - 1 根返回 NaN（热身期）。
    完全横盘时 +DI / -DI 均为 NaN，ADX 也为 NaN（无方向，视为非趋势）。
    """
    high = df["high"].to_numpy(dtype=float)
    low  = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)

    prev_high  = np.roll(high, 1);  prev_high[0]  = np.nan
    prev_low   = np.roll(low, 1);   prev_low[0]   = np.nan
    prev_close = np.roll(close, 1); prev_close[0] = np.nan

    tr = np.maximum.reduce([
        high - low,
        np.abs(high - prev_close),
        np.abs(low  - prev_close),
    ])
    tr[0] = np.nan

    up_move   = high - prev_high
    down_move = prev_low - low

    plus_dm  = np.where((up_move > down_move)   & (up_move > 0),   up_move,   0.0)
    minus_dm = np.where((down_move > up_move)   & (down_move > 0), down_move, 0.0)
    plus_dm[0] = minus_dm[0] = np.nan

    # 用 _wilder_smooth：稳态 = N×均值，比值时 N 约掉，DI 正确
    atr_w      = _wilder_smooth(tr,       period)
    plus_dm_w  = _wilder_smooth(plus_dm,  period)
    minus_dm_w = _wilder_smooth(minus_dm, period)

    with np.errstate(invalid="ignore", divide="ignore"):
        plus_di  = 100.0 * plus_dm_w  / atr_w
        minus_di = 100.0 * minus_dm_w / atr_w
        di_sum   = plus_di + minus_di
        dx = np.where(di_sum > 0, 100.0 * np.abs(plus_di - minus_di) / di_sum, np.nan)

    # 用 _rma：ADX 稳态 = DX 均值，值域 [0, 100]
    adx_arr = _rma(dx, period)
    return pd.Series(adx_arr, index=df.index, name="adx")
