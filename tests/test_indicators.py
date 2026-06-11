"""
ADX 指标单元测试
"""
import numpy as np
import pandas as pd
import pytest

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from indicators import adx, _wilder_smooth


def _make_ohlcv(closes: list[float]) -> pd.DataFrame:
    """用收盘价序列构造最简 OHLCV（high=close, low=close）。"""
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="1h", tz="UTC")
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1.0}, index=idx)


def _make_ohlcv_trend(n: int = 100, step: float = 10.0) -> pd.DataFrame:
    """单调上涨行情，ADX 应随趋势走高。"""
    closes = [1000.0 + i * step for i in range(n)]
    highs  = [c + step * 0.3 for c in closes]
    lows   = [c - step * 0.3 for c in closes]
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes, "volume": 1.0}, index=idx)


def _make_ohlcv_flat(n: int = 100) -> pd.DataFrame:
    """完全横盘（high=low=close），+DM/-DM 全为 0，ADX 应趋近 0。"""
    closes = [1000.0] * n
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1.0}, index=idx)


# ── Wilder 平滑 ───────────────────────────────────────────────────────────────

class TestWilderSmooth:
    def test_seed_equals_sum(self):
        """种子值 = 前 period 根之和"""
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        out = _wilder_smooth(arr, period=3)
        assert out[2] == pytest.approx(6.0)  # 1+2+3

    def test_recursion(self):
        """第 period+1 根 = seed - seed/period + arr[period]"""
        arr = np.array([1.0, 2.0, 3.0, 4.0])
        out = _wilder_smooth(arr, period=3)
        seed = 6.0
        expected = seed - seed / 3 + 4.0
        assert out[3] == pytest.approx(expected)

    def test_leading_nan(self):
        """前 period-1 根应为 NaN"""
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        out = _wilder_smooth(arr, period=3)
        assert np.isnan(out[0])
        assert np.isnan(out[1])
        assert not np.isnan(out[2])

    def test_insufficient_data_all_nan(self):
        arr = np.array([1.0, 2.0])
        out = _wilder_smooth(arr, period=5)
        assert np.all(np.isnan(out))


# ── ADX 基本属性 ──────────────────────────────────────────────────────────────

class TestAdx:
    def test_output_length_matches_input(self):
        df = _make_ohlcv_trend(60)
        result = adx(df, period=14)
        assert len(result) == len(df)

    def test_index_matches_input(self):
        df = _make_ohlcv_trend(60)
        result = adx(df, period=14)
        assert result.index.equals(df.index)

    def test_warmup_period_is_nan(self):
        """前 2*period-2 根应为 NaN（两次 Wilder 平滑各需 period 根）。"""
        df = _make_ohlcv_trend(60)
        result = adx(df, period=14)
        # 第 0..26 根必须是 NaN（2*14-2=26）
        assert result.iloc[:27].isna().all(), "热身期应全为 NaN"

    def test_non_negative_after_warmup(self):
        df = _make_ohlcv_trend(60)
        result = adx(df, period=14)
        valid = result.dropna()
        assert (valid >= 0).all()

    def test_trend_adx_is_high(self):
        """强趋势行情（单调上涨）的 ADX 应显著高于 50。"""
        df = _make_ohlcv_trend(100, step=50.0)
        result = adx(df, 14).dropna()
        assert len(result) > 0
        assert result.mean() > 50, f"趋势 ADX 均值={result.mean():.1f} 应 > 50"

    def test_flat_adx_is_nan(self):
        """完全横盘（zero-range）时 TR=0 → +DI/-DI=0/0=NaN → ADX 全为 NaN。
        run_signals 中 NaN ADX 视为「非趋势」，允许入场。"""
        df = _make_ohlcv_flat(100)
        result = adx(df, 14)
        assert result.isna().all(), "零振幅行情 ADX 应全为 NaN"
