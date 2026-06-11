"""
集中参数表 — 对应 STRATEGY.md 第 8 节
回测时只改这里，不动策略逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    # ── 区间识别（1h）──────────────────────────────────
    N: int = 48                  # 回看窗口（1h 根数，约 2 天）
    adx_len: int = 14            # ADX 周期
    adx_thresh: float = 25.0     # ADX < thresh 才视为震荡

    # ── 入场容差（15m 触发）─────────────────────────────
    edge_buffer: float = 0.005   # 0.5%：贴近边沿才入场

    # ── 出场参数 ────────────────────────────────────────
    stop_buffer: float = 0.01    # 1%：区间突破止损容差
    tp_mode: str = "mid"         # "mid"=中线止盈 | "opposite"=对侧边沿
    max_hold_days: Optional[int] = None  # 时间止损（天），None=不限时，持到止盈/止损

    # ── 仓位 ────────────────────────────────────────────
    risk_per_trade: float = 0.01 # 单笔风险（账户权益的 1%）
    max_leverage: float = 5.0    # 杠杆上限

    # ── 层开关 ───────────────────────────────────────────
    chan_on: bool = False         # 缠论层
    liuyao_on: bool = False       # 六爻层
    # 两层同时开启时的组合逻辑：
    #   True  = AND：缠论与六爻必须同向（版本 F）
    #   False = OR：任意一层放行即可，六爻观望不拦截（版本 G）
    chan_liuyao_and: bool = True
    tikeyong_bullish: bool = False


# ── 生产配置（已回测验证） ─────────────────────────────────────────────────────
# ETH：版本 F，N=48（2天窗口），检验段 Sharpe=2.14，期望值+1.25%/笔
ETH_LIVE = Config(
    tp_mode="opposite",
    chan_on=True,
    liuyao_on=True,
    chan_liuyao_and=True,
    N=48,
    adx_thresh=25.0,
)

# BTC：BTC-B，N=24（1天窗口），检验段 Sharpe=1.12，期望值+0.22%/笔
BTC_LIVE = Config(
    tp_mode="opposite",
    chan_on=True,
    liuyao_on=True,
    chan_liuyao_and=True,
    N=24,
    adx_thresh=25.0,
)
