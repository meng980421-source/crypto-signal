"""
OKX 公开行情拉取 — 永续合约 K 线（分页版）
支持 BTC/USDT:USDT 和 ETH/USDT:USDT，不需要 API key。
结果缓存到 cache/<symbol>_<timeframe>.parquet。

周期说明：
  15m — 信号判断周期，拉 2 年历史（≈70000 根，OKX 不够就拉到最早）
  1h  — 区间 + ADX 计算，拉 2 年（与 15m 覆盖相同时间跨度）
  1d  — 大环境参考，拉到 OKX 最早可用历史
"""

from __future__ import annotations

import time
from pathlib import Path

import ccxt
import pandas as pd

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
TIMEFRAMES = ["15m", "1h", "1d"]

# days_back=None → 从 _EARLIEST_MS 开始拉到最早
_TF_CONFIG: dict[str, dict] = {
    "15m": {"days_back": 730,  "batch": 300},
    "1h":  {"days_back": 730,  "batch": 300},
    "1d":  {"days_back": None, "batch": 300},
}

# OKX BTC/USDT:USDT 永续约 2019-11 上线，用 2020-01-01 确保有数据
_EARLIEST_MS = int(pd.Timestamp("2020-01-01", tz="UTC").timestamp() * 1000)

CACHE_DIR = Path(__file__).parent.parent / "cache"

class _OkxExchange(ccxt.okx):
    """ccxt.okx subclass that tolerates None keys in markets_by_id (OKX quirk)."""
    def keysort(self, d: dict) -> dict:
        return dict(sorted(d.items(), key=lambda kv: (kv[0] is None, kv[0] or "")))


_exchange: _OkxExchange | None = None


def _get_exchange() -> _OkxExchange:
    global _exchange
    if _exchange is None:
        _exchange = _OkxExchange({"enableRateLimit": True})
    return _exchange


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "-").replace(":", "_")


def _raw_to_df(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates(subset="timestamp")
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df.set_index("timestamp").sort_index().astype(float)


def _fetch_paginated(symbol: str, timeframe: str, since_ms: int, batch: int = 300) -> pd.DataFrame:
    """
    从 since_ms 逐批向后拉取直到当前时间。
    每 10 批打印一次进度，防止相同 last_ts 时死循环。
    """
    ex = _get_exchange()
    now_ms = int(pd.Timestamp.utcnow().timestamp() * 1000)
    all_rows: list = []
    n_req = 0
    prev_last_ts = -1

    while since_ms < now_ms:
        try:
            fetched = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=batch)
        except ccxt.RateLimitExceeded:
            time.sleep(2)
            continue

        n_req += 1

        if not fetched:
            break

        all_rows.extend(fetched)
        last_ts = fetched[-1][0]

        # 防死循环：OKX 有时最后一批反复返回同一截止时间
        if last_ts == prev_last_ts:
            break
        prev_last_ts = last_ts

        # 每 10 次请求打印进度
        if n_req % 10 == 0:
            cur_date = pd.Timestamp(last_ts, unit="ms", tz="UTC").date()
            print(f"\r    [{n_req:>3} 批] {len(all_rows):>6} 根  当前: {cur_date}  ", end="", flush=True)

        # 已追上当前 or 最后一批不满，结束
        if last_ts >= now_ms or len(fetched) < batch:
            break

        since_ms = last_ts + 1
        time.sleep(0.2)          # ~5 req/s，公共接口安全阈值

    # 清空进度行
    print("\r" + " " * 60 + "\r", end="", flush=True)
    return _raw_to_df(all_rows)


def fetch_ohlcv(symbol: str, timeframe: str) -> pd.DataFrame:
    """按 _TF_CONFIG 拉取指定周期的完整历史。"""
    cfg = _TF_CONFIG[timeframe]
    if cfg["days_back"] is not None:
        since_ms = int(
            (pd.Timestamp.utcnow() - pd.Timedelta(days=cfg["days_back"])).timestamp() * 1000
        )
    else:
        since_ms = _EARLIEST_MS
    return _fetch_paginated(symbol, timeframe, since_ms, batch=cfg["batch"])


def refresh_cache(
    symbols: list[str] = SYMBOLS,
    timeframes: list[str] = TIMEFRAMES,
) -> dict[str, pd.DataFrame]:
    """拉取所有品种 × 周期并写 parquet，返回 {key: df}。"""
    CACHE_DIR.mkdir(exist_ok=True)
    result: dict[str, pd.DataFrame] = {}

    for sym in symbols:
        for tf in timeframes:
            cfg = _TF_CONFIG[tf]
            label = f"2年分页" if cfg["days_back"] == 730 else "全量分页"
            print(f"  拉取 {sym} [{tf}] ({label}) ...")

            df = fetch_ohlcv(sym, tf)

            if df.empty:
                print(f"  ⚠ 返回空数据，跳过 {sym} {tf}\n")
                continue

            key = f"{_safe_symbol(sym)}_{tf}"
            path = CACHE_DIR / f"{key}.parquet"
            df.to_parquet(path)
            result[key] = df

            span = f"{df.index[0].date()} ~ {df.index[-1].date()}"
            print(f"  ✓ {len(df):>6} 根  {span}\n")
            time.sleep(0.3)

    return result


def load_cache(symbol: str, timeframe: str) -> pd.DataFrame:
    """从 parquet 读取缓存，不存在则先拉取。"""
    key = f"{_safe_symbol(symbol)}_{timeframe}"
    path = CACHE_DIR / f"{key}.parquet"
    if not path.exists():
        print(f"缓存不存在，先拉取 {symbol} {timeframe} ...")
        refresh_cache([symbol], [timeframe])
    return pd.read_parquet(path)
