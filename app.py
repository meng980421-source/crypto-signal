"""
加密信号监控面板（Streamlit）

运行：
    streamlit run app.py

功能：
    顶部   BTC / ETH 实时价格（每 15 秒自动刷新）
    中部   当前持仓状态（入场价 / 止损价 / 止盈价 / 浮盈）
    底部   历史信号记录（最近 20 笔）
"""
from __future__ import annotations

import time
import pandas as pd
import streamlit as st

# ── 页面配置 ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Crypto Signal Monitor",
    page_icon="📊",
    layout="wide",
)

# ── 数据源（现为假数据；接入真实信号后替换这里）────────────────────────────────

def get_prices() -> dict[str, float]:
    """实时价格 —— 目前返回占位数据，后续替换为 ccxt 行情。"""
    try:
        from data.okx_feed import load_cache
        btc = load_cache("BTC/USDT:USDT", "15m").iloc[-1]["close"]
        eth = load_cache("ETH/USDT:USDT", "15m").iloc[-1]["close"]
        return {"BTC": float(btc), "ETH": float(eth)}
    except Exception:
        return {"BTC": 105_000.0, "ETH": 2_500.0}


def get_positions() -> list[dict]:
    """当前持仓 —— 目前返回模拟数据。"""
    return [
        {
            "symbol":      "ETH/USDT:USDT",
            "direction":   "空",
            "entry_time":  "2026-06-09 14:00",
            "entry_price": 2_450.00,
            "stop_price":  2_485.00,
            "tp_price":    2_350.00,
            "current":     2_440.00,   # 当前价（用于计算浮盈）
        },
    ]


def get_signal_history() -> pd.DataFrame:
    """历史信号记录 —— 目前返回模拟数据（最近 20 笔）。"""
    mock = [
        ("2026-05-21 00:45", "ETH", "空", 2142.01, 2170.06, 2092.40, "2026-05-22 19:00", "止盈", "+1.64%"),
        ("2026-05-12 06:45", "ETH", "多", 2303.04, 2270.97, 2383.11, "2026-05-12 13:45", "止损", "-1.09%"),
        ("2026-05-09 19:00", "ETH", "空", 2328.97, 2361.12, 2262.45, "2026-05-10 17:45", "止损", "-1.11%"),
        ("2026-02-21 16:30", "ETH", "空", 1988.04, 2015.71, 1905.69, "2026-02-23 01:00", "止盈", "+2.86%"),
        ("2025-12-23 07:00", "ETH", "多", 2956.99, 2913.01, 3077.16, "2025-12-23 17:45", "止损", "-1.09%"),
        ("2025-12-18 20:45", "ETH", "多", 2780.18, 2744.36, 3029.50, "2025-12-22 00:00", "止盈", "+6.79%"),
        ("2025-10-19 11:00", "ETH", "空", 3944.33, 3996.71, 3711.44, "2025-10-19 17:00", "止损", "-1.10%"),
        ("2025-09-08 00:15", "ETH", "空", 4315.11, 4379.36, 4230.00, "2025-09-08 15:15", "止损", "-1.09%"),
        ("2025-09-06 15:00", "ETH", "多", 4270.72, 4210.80, 4495.00, "2025-09-12 00:30", "止盈", "+3.54%"),
        ("2025-08-31 08:30", "ETH", "空", 4470.65, 4534.50, 4255.16, "2025-09-01 21:30", "止盈", "+3.26%"),
        ("2025-08-27 15:45", "ETH", "空", 4654.80, 4712.84, 4308.80, "2025-08-29 14:00", "止盈", "+5.82%"),
        ("2025-07-27 02:45", "ETH", "空", 3783.49, 3832.34, 3572.17, "2025-07-27 12:00", "止损", "-1.10%"),
        ("2025-06-16 01:45", "ETH", "空", 2553.20, 2591.66, 2486.31, "2025-06-16 05:15", "止损", "-1.08%"),
    ]
    df = pd.DataFrame(mock, columns=[
        "入场时间", "币种", "方向", "入场价", "止损价", "止盈价",
        "出场时间", "出场原因", "盈亏",
    ])
    return df.head(20)


# ── UI 渲染 ───────────────────────────────────────────────────────────────────

def _pnl_color(pnl_str: str) -> str:
    return "color:green" if pnl_str.startswith("+") else "color:red"


def render() -> None:
    st.title("📊 Crypto Signal Monitor")
    st.caption(f"最后刷新：{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}  （每 15 秒自动刷新）")

    # ── 顶部：实时价格 ────────────────────────────────────────────────────────
    st.subheader("实时价格")
    prices = get_prices()
    col_btc, col_eth, col_pad = st.columns([1, 1, 2])
    with col_btc:
        st.metric("BTC / USDT", f"${prices['BTC']:,.0f}")
    with col_eth:
        st.metric("ETH / USDT", f"${prices['ETH']:,.2f}")

    st.divider()

    # ── 中部：当前持仓 ────────────────────────────────────────────────────────
    st.subheader("当前持仓")
    positions = get_positions()
    if not positions:
        st.info("暂无持仓")
    else:
        for pos in positions:
            sym    = pos["symbol"].split("/")[0]
            cur    = prices.get(sym, pos["current"])
            if pos["direction"] == "多":
                unreal_pct = (cur - pos["entry_price"]) / pos["entry_price"] * 100
            else:
                unreal_pct = (pos["entry_price"] - cur) / pos["entry_price"] * 100

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("币种 / 方向", f"{sym}  {pos['direction']}")
            c2.metric("入场价", f"{pos['entry_price']:,.2f}")
            c3.metric("止损价", f"{pos['stop_price']:,.2f}")
            c4.metric("止盈价", f"{pos['tp_price']:,.2f}")
            delta_str = f"{unreal_pct:+.2f}%"
            c5.metric("浮盈亏", delta_str, delta=delta_str)

    st.divider()

    # ── 底部：历史记录 ────────────────────────────────────────────────────────
    st.subheader("历史信号记录（最近 20 笔）")
    df = get_signal_history()

    # 对盈亏列着色
    def _style_row(row: pd.Series) -> list[str]:
        styles = [""] * len(row)
        idx = df.columns.get_loc("盈亏")
        val = row.iloc[idx]
        styles[idx] = "color: green; font-weight:bold" if val.startswith("+") else "color: red"
        return styles

    styled = df.style.apply(_style_row, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ── 自动刷新循环 ──────────────────────────────────────────────────────────────
render()
time.sleep(15)
st.rerun()
