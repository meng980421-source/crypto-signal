"""
Firebase Cloud Messaging 推送（Android APP）

配置：在项目根目录 .env 文件中添加：
  FCM_DEVICE_TOKEN=your_device_token_here   # 从 APP 右上角铃铛图标复制

依赖：
  pip install firebase-admin
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

_DEVICE_TOKEN = os.getenv("FCM_DEVICE_TOKEN", "")
_KEY_FILE = Path(__file__).parent.parent / "firebase-key.json"

# 懒初始化，避免 firebase-admin 未安装时报错
_app = None


def _get_app():
    global _app
    if _app is not None:
        return _app
    try:
        import firebase_admin
        from firebase_admin import credentials
        if not _KEY_FILE.exists():
            raise FileNotFoundError(f"firebase-key.json 不存在: {_KEY_FILE}")
        cred = credentials.Certificate(str(_KEY_FILE))
        _app = firebase_admin.initialize_app(cred)
    except Exception as exc:
        print(f"[fcm] 初始化失败: {exc}")
        _app = None
    return _app


def _send(title: str, body: str, data: dict) -> bool:
    if not _DEVICE_TOKEN:
        print(f"[fcm] FCM_DEVICE_TOKEN 未设置，仅打印:\n  {title}\n  {body}")
        return False
    if _get_app() is None:
        return False
    try:
        from firebase_admin import messaging
        msg = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in data.items()},
            android=messaging.AndroidConfig(priority="high"),
            token=_DEVICE_TOKEN,
        )
        messaging.send(msg)
        print(f"[fcm] 推送成功: {title}")
        return True
    except Exception as exc:
        print(f"[fcm] 发送失败: {exc}")
        return False


def notify_entry(
    symbol: str,
    direction: str,   # "long" | "short"
    entry: float,
    stop: float,
    tp: float,
) -> bool:
    sym = symbol.split("/")[0]
    dir_cn = "做多 📈" if direction == "long" else "做空 📉"
    rr = abs(tp - entry) / abs(stop - entry) if abs(stop - entry) > 1e-9 else 0.0
    title = f"🚨 {sym} 入场信号 — {dir_cn}"
    body = f"入场: ${entry:.2f}  止损: ${stop:.2f}  止盈: ${tp:.2f}  RR: {rr:.2f}"
    return _send(title, body, {
        "type":      "new_signal",
        "symbol":    sym,
        "direction": direction,
        "entry":     f"{entry:.2f}",
        "stop":      f"{stop:.2f}",
        "tp":        f"{tp:.2f}",
    })


def notify_exit(
    symbol: str,
    direction: str,   # "long" | "short"
    reason: str,      # "sl" | "tp" | "time"
    pnl_pct: float,
) -> bool:
    sym = symbol.split("/")[0]
    dir_cn = "多单" if direction == "long" else "空单"
    reason_map = {"sl": "止损 ❌", "tp": "止盈 ✅", "time": "超时平仓 ⏰"}
    reason_cn = reason_map.get(reason, reason)
    sign = "+" if pnl_pct >= 0 else ""
    title = f"{'✅' if pnl_pct > 0 else '❌'} {sym} {dir_cn}离场 — {reason_cn}"
    body = f"盈亏: {sign}{pnl_pct:.2f}%"
    return _send(title, body, {
        "type":      "exit_signal",
        "symbol":    sym,
        "direction": direction,
        "reason":    reason,
        "pnl_pct":   f"{pnl_pct:.2f}",
    })


# ── 快速自测 ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("测试入场推送（无 TOKEN 时仅打印）：")
    notify_entry("ETH/USDT:USDT", "short", 2553.20, 2591.66, 2486.31)
    print("\n测试离场推送：")
    notify_exit("ETH/USDT:USDT", "short", "tp", 5.82)
