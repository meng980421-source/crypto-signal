"""
区间策略单元测试：区间边界、入场触发、止损触发
"""
import numpy as np
import pandas as pd
import pytest

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from config import Config
from strategy.range_strategy import Signal, run_signals, _range_at


# ── 构造辅助函数 ──────────────────────────────────────────────────────────────

def _h1_df(highs: list[float], lows: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    n = len(highs)
    closes = [(h + l) / 2 for h, l in zip(highs, lows)]
    idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {"open": closes, "high": highs, "low": lows, "close": closes, "volume": 1.0},
        index=idx,
    )


def _h15m_bar(ts: str, close: float) -> pd.DataFrame:
    """单根 15m K 线。"""
    idx = pd.DatetimeIndex([pd.Timestamp(ts, tz="UTC")])
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1.0},
        index=idx,
    )


def _make_flat_h1(n: int = 100, high: float = 110.0, low: float = 90.0) -> pd.DataFrame:
    """
    n 根横盘 1h K 线：高点固定=high，低点固定=low。
    ADX 在横盘行情下会趋近 0，满足震荡过滤条件。
    """
    return _h1_df([high] * n, [low] * n)


def _make_15m_stream(closes: list[float], start: str = "2024-01-05 00:00") -> pd.DataFrame:
    """连续 15m K 线流，从 start 开始。"""
    idx = pd.date_range(start, periods=len(closes), freq="15min", tz="UTC")
    c = np.array(closes, dtype=float)
    return pd.DataFrame(
        {"open": c, "high": c, "low": c, "close": c, "volume": 1.0},
        index=idx,
    )


# ── _range_at ─────────────────────────────────────────────────────────────────

class TestRangeAt:
    def test_upper_lower_mid(self):
        """上沿=窗口最高，下沿=窗口最低，中线=均值。"""
        df = _h1_df(highs=[100, 110, 105], lows=[90, 85, 95])
        upper, lower, mid = _range_at(df, N=3)
        assert upper == pytest.approx(110.0)
        assert lower == pytest.approx(85.0)
        assert mid   == pytest.approx(97.5)

    def test_window_uses_last_n_bars(self):
        """N=2 时只取最后 2 根。"""
        df = _h1_df(highs=[200, 110, 105], lows=[10, 85, 95])
        upper, lower, mid = _range_at(df, N=2)
        assert upper == pytest.approx(110.0)
        assert lower == pytest.approx(85.0)


# ── 入场条件 ──────────────────────────────────────────────────────────────────

class TestEntryConditions:
    """
    用充足的横盘 1h 数据（ADX 接近 0）+ 单根 15m K 线验证入场条件。
    """

    def _run_one_bar(self, close_15m: float, high_1h: float = 110.0, low_1h: float = 90.0) -> list[Signal]:
        cfg = Config(N=48, edge_buffer=0.005, stop_buffer=0.01)
        h1 = _make_flat_h1(n=100, high=high_1h, low=low_1h)
        # 15m bar 在 1h 数据结束后 15m（确保有足够历史）
        start_15m = (h1.index[-1] + pd.Timedelta("15min")).isoformat()
        h15m = _make_15m_stream([close_15m], start=start_15m)
        return run_signals("BTC", h15m, h1, cfg)

    def test_long_entry_triggered(self):
        """收盘 = 下沿 × 1.003 ≤ 下沿 × 1.005 → 触发做多。"""
        sigs = self._run_one_bar(close_15m=90.0 * 1.003)
        assert len(sigs) == 1
        assert sigs[0].direction == "long"

    def test_long_entry_at_lower_exact(self):
        """收盘 = 下沿本身 → 触发做多。"""
        sigs = self._run_one_bar(close_15m=90.0)
        assert any(s.direction == "long" for s in sigs)

    def test_long_entry_not_triggered(self):
        """收盘 = 下沿 × 1.008 > 下沿 × 1.005 → 不触发做多。"""
        sigs = self._run_one_bar(close_15m=90.0 * 1.008)
        long_sigs = [s for s in sigs if s.direction == "long"]
        assert len(long_sigs) == 0

    def test_short_entry_triggered(self):
        """收盘 = 上沿 × 0.997 ≥ 上沿 × 0.995 → 触发做空。"""
        sigs = self._run_one_bar(close_15m=110.0 * 0.997)
        assert len(sigs) == 1
        assert sigs[0].direction == "short"

    def test_short_entry_not_triggered(self):
        """收盘 = 上沿 × 0.990 < 上沿 × 0.995 → 不触发做空。"""
        sigs = self._run_one_bar(close_15m=110.0 * 0.990)
        short_sigs = [s for s in sigs if s.direction == "short"]
        assert len(short_sigs) == 0

    def test_signal_prices(self):
        """止损=下沿×0.99，止盈=中线=(110+90)/2=100。"""
        sigs = self._run_one_bar(close_15m=90.0 * 1.003)
        assert len(sigs) == 1
        s = sigs[0]
        assert s.stop_price == pytest.approx(90.0 * 0.99, rel=1e-6)
        assert s.tp_price   == pytest.approx(100.0, rel=1e-6)


# ── 同方向不重复开仓 ──────────────────────────────────────────────────────────

class TestNoDoubleEntry:
    def test_no_duplicate_long(self):
        """连续多根 15m 都贴近下沿，只发 1 个做多信号（仓位未平仓时）。"""
        cfg = Config(N=48, edge_buffer=0.005, stop_buffer=0.01, max_hold_days=5)
        h1 = _make_flat_h1(n=100)
        start = (h1.index[-1] + pd.Timedelta("15min")).isoformat()
        # 10 根都在下沿附近
        closes = [90.0 * 1.002] * 10
        h15m = _make_15m_stream(closes, start=start)
        sigs = run_signals("BTC", h15m, h1, cfg)
        long_sigs = [s for s in sigs if s.direction == "long"]
        assert len(long_sigs) == 1


# ── 止损触发 ──────────────────────────────────────────────────────────────────

class TestStopLoss:
    def test_long_stop_loss_allows_reentry(self):
        """
        做多开仓后价格跌穿止损 → 仓位关闭 → 再次贴近下沿时允许重新开多。
        """
        cfg = Config(N=48, edge_buffer=0.005, stop_buffer=0.01, max_hold_days=5)
        h1 = _make_flat_h1(n=100, high=110.0, low=90.0)
        start = (h1.index[-1] + pd.Timedelta("15min")).isoformat()

        # 序列：触发入场 → 跌穿止损(89.0 < 90×0.99=89.1) → 再次触发入场
        closes = [
            90.0 * 1.002,   # 触发做多入场
            89.0,           # 跌穿止损（89 < 89.1）→ 平仓
            90.0 * 1.002,   # 重新入场
        ]
        h15m = _make_15m_stream(closes, start=start)
        sigs = run_signals("BTC", h15m, h1, cfg)
        long_sigs = [s for s in sigs if s.direction == "long"]
        assert len(long_sigs) == 2, f"期望 2 次做多信号，实际 {len(long_sigs)}"

    def test_short_stop_loss_allows_reentry(self):
        """
        做空开仓后价格升破止损 → 仓位关闭 → 再次贴近上沿时允许重新开空。
        """
        cfg = Config(N=48, edge_buffer=0.005, stop_buffer=0.01, max_hold_days=5)
        h1 = _make_flat_h1(n=100, high=110.0, low=90.0)
        start = (h1.index[-1] + pd.Timedelta("15min")).isoformat()

        closes = [
            110.0 * 0.997,  # 触发做空入场
            111.2,          # 升破止损（111.2 > 110×1.01=111.1）→ 平仓
            110.0 * 0.997,  # 重新入场
        ]
        h15m = _make_15m_stream(closes, start=start)
        sigs = run_signals("BTC", h15m, h1, cfg)
        short_sigs = [s for s in sigs if s.direction == "short"]
        assert len(short_sigs) == 2, f"期望 2 次做空信号，实际 {len(short_sigs)}"


# ── ADX 震荡过滤 ──────────────────────────────────────────────────────────────

class TestAdxFilter:
    def test_trending_market_no_entry(self):
        """
        强趋势行情（ADX >> 25）不应产生入场信号。
        构造单调上涨 1h 数据，ADX 必然高于阈值。
        """
        cfg = Config(N=48, adx_thresh=25.0, edge_buffer=0.005)
        n = 200
        # 单调上涨，每小时涨 50
        highs  = [1000.0 + i * 50 + 10 for i in range(n)]
        lows   = [1000.0 + i * 50 - 10 for i in range(n)]
        h1 = _h1_df(highs, lows)

        # 15m 收盘贴近"当前下沿"
        start = (h1.index[-1] + pd.Timedelta("15min")).isoformat()
        # 最后 N 根的最低价
        lower = min(lows[-cfg.N:])
        h15m = _make_15m_stream([lower * 1.002], start=start)

        sigs = run_signals("BTC", h15m, h1, cfg)
        assert len(sigs) == 0, "趋势行情下不应产生信号"
