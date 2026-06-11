"""
PushPlus 微信推送

使用前：在项目根目录建 .env 文件，写入：
  PUSHPLUS_TOKEN=your_token_here

推送类型：
  notify_entry()  —— 入场信号
  notify_exit()   —— 离场通知
"""
from __future__ import annotations

import os
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

_TOKEN   = os.getenv("PUSHPLUS_TOKEN", "")
_API_URL = "https://www.pushplus.plus/send"
_TIMEOUT = 10


def _send(title: str, content: str) -> bool:
    """底层发送，返回是否成功。TOKEN 缺失时仅打印到控制台。"""
    if not _TOKEN:
        print(f"[pushplus] TOKEN 未设置，仅打印:\n  {title}\n  {content}")
        return False
    try:
        resp = requests.post(
            _API_URL,
            json={"token": _TOKEN, "title": title,
                  "content": content, "template": "html"},
            timeout=_TIMEOUT,
        )
        data = resp.json()
        if data.get("code") == 200:
            return True
        print(f"[pushplus] 推送失败: {data}")
        return False
    except Exception as exc:
        print(f"[pushplus] 请求异常: {exc}")
        return False


def notify_entry(
    symbol:    str,
    direction: str,   # "long" | "short"
    entry:     float,
    stop:      float,
    tp:        float,
) -> bool:
    """入场信号推送。"""
    sym    = symbol.split("/")[0]
    dir_cn = "做多 📈" if direction == "long" else "做空 📉"
    rr     = abs(tp - entry) / abs(stop - entry) if abs(stop - entry) > 1e-9 else 0.0
    title  = f"🚨 {sym} 入场信号 — {dir_cn}"
    content = (
        f"<b>币种：</b>{sym}<br>"
        f"<b>方向：</b>{dir_cn}<br>"
        f"<hr>"
        f"<b>入场价：</b>{entry:.2f} USDT<br>"
        f"<b>止损价：</b>{stop:.2f} USDT<br>"
        f"<b>止盈价：</b>{tp:.2f} USDT<br>"
        f"<b>盈亏比：</b>{rr:.2f}"
    )
    return _send(title, content)


def notify_exit(
    symbol:    str,
    direction: str,    # "long" | "short"
    reason:    str,    # "sl" | "tp" | "time"
    pnl_pct:   float,
) -> bool:
    """离场通知推送。"""
    sym    = symbol.split("/")[0]
    dir_cn = "多单" if direction == "long" else "空单"
    reason_map = {"sl": "止损 ❌", "tp": "止盈 ✅", "time": "超时平仓 ⏰"}
    reason_cn  = reason_map.get(reason, reason)
    emoji  = "✅" if pnl_pct > 0 else "❌"
    sign   = "+" if pnl_pct >= 0 else ""
    title  = f"{emoji} {sym} 离场 — {reason_cn}"
    content = (
        f"<b>币种：</b>{sym}<br>"
        f"<b>方向：</b>{dir_cn}<br>"
        f"<b>出场原因：</b>{reason_cn}<br>"
        f"<b>盈亏：</b>{sign}{pnl_pct:.2f}%"
    )
    return _send(title, content)


# ── 快速自测 ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("测试入场推送（无 TOKEN 时仅打印）：")
    notify_entry("ETH/USDT:USDT", "short", 2553.20, 2591.66, 2486.31)
    print("\n测试离场推送：")
    notify_exit("ETH/USDT:USDT", "short", "tp", 5.82)
