"""
验收入口：刷新行情缓存，打印每个周期的根数、起止日期、最新一根 K 线。
"""

from data.okx_feed import SYMBOLS, TIMEFRAMES, refresh_cache, load_cache


def main() -> None:
    print("=" * 60)
    print("正在刷新行情缓存（15m/1h 各约 2 年，1d 全量）...")
    print("=" * 60)
    refresh_cache(SYMBOLS, TIMEFRAMES)

    print("=" * 60)
    print("行情摘要（各周期最新一根）")
    print("=" * 60)

    for sym in SYMBOLS:
        print(f"\n▶ {sym}")
        for tf in TIMEFRAMES:
            df = load_cache(sym, tf)
            last = df.iloc[-1]
            span = f"{df.index[0].date()} ~ {df.index[-1].date()}"
            print(
                f"  [{tf:>3}] {len(df):>6} 根  {span}"
                f"  | 收盘: {last['close']:>10,.2f}"
                f"  | 高: {last['high']:>10,.2f}  低: {last['low']:>10,.2f}"
                f"  | 时间(UTC): {df.index[-1]}"
            )


if __name__ == "__main__":
    main()
