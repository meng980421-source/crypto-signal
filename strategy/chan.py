"""
缠论背驰检测（基于 MACD 面积比较，czsc 背驰信号的数值核心）

底背驰：最近两个局部低点，价格更低但 MACD 柱面积更小（绝对值）→ bull
顶背驰：最近两个局部高点，价格更高但 MACD 柱面积更小（绝对值）→ bear
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _macd_hist(close: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9) -> pd.Series:
    dif = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    dea = dif.ewm(span=sig, adjust=False).mean()
    return dif - dea


def _local_extrema(arr: np.ndarray, w: int, find_min: bool) -> np.ndarray:
    """返回局部极值（极小或极大）的下标数组。"""
    n = len(arr)
    idxs = []
    for i in range(w, n - w):
        window = arr[i - w: i + w + 1]
        if find_min:
            if arr[i] == window.min():
                idxs.append(i)
        else:
            if arr[i] == window.max():
                idxs.append(i)
    return np.array(idxs, dtype=np.int64)


def compute_chan_signals(
    h1: pd.DataFrame,
    lookback: int = 80,
    swing_w:  int = 4,
) -> pd.Series:
    """
    对 h1 每根 K 线预计算背驰方向。

    Returns
    -------
    pd.Series  index=h1.index, values: 'bull' | 'bear' | 'none'
    """
    lo_arr   = h1["low"].values
    hi_arr   = h1["high"].values
    hist_arr = _macd_hist(h1["close"]).values
    n        = len(h1)

    # 全量极值索引（只算一次）
    all_lo = _local_extrema(lo_arr,  swing_w, find_min=True)
    all_hi = _local_extrema(hi_arr, swing_w, find_min=False)

    sig = np.full(n, "none", dtype=object)

    for i in range(lookback, n):
        lo_in = all_lo[(all_lo >= i - lookback) & (all_lo <= i)]
        if len(lo_in) >= 2:
            j1, j2 = lo_in[-2], lo_in[-1]
            if (j2 >= i - swing_w * 2           # 极值足够新
                    and lo_arr[j2]  < lo_arr[j1]   # 价格更低
                    and hist_arr[j2] > hist_arr[j1]):  # MACD 柱更高（底背驰）
                sig[i] = "bull"
                continue

        hi_in = all_hi[(all_hi >= i - lookback) & (all_hi <= i)]
        if len(hi_in) >= 2:
            j1, j2 = hi_in[-2], hi_in[-1]
            if (j2 >= i - swing_w * 2
                    and hi_arr[j2]  > hi_arr[j1]
                    and hist_arr[j2] < hist_arr[j1]):   # MACD 柱更低（顶背驰）
                sig[i] = "bear"

    return pd.Series(sig, index=h1.index, name="chan_signal")
