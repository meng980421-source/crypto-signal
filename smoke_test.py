"""
冒烟测试：在最近 30 天数据上跑区间信号，打印所有入场信号。
"""
import pandas as pd

from config import Config
from data.okx_feed import SYMBOLS, load_cache
from strategy.range_strategy import run_signals

SMOKE_DAYS = 30


def main() -> None:
    cfg = Config()
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=SMOKE_DAYS)

    print("=" * 65)
    print(f"冒烟测试：最近 {SMOKE_DAYS} 天区间信号（区间层，缠论/六爻关闭）")
    print(f"参数：N={cfg.N}根1h  ADX阈值={cfg.adx_thresh}  "
          f"edge={cfg.edge_buffer*100:.1f}%  stop={cfg.stop_buffer*100:.1f}%  "
          f"tp={cfg.tp_mode}  最大持仓={cfg.max_hold_days}天")
    print("=" * 65)

    for sym in SYMBOLS:
        h15m_full = load_cache(sym, "15m")
        h1_full   = load_cache(sym, "1h")

        # 1h 保留完整历史（ADX/区间需要热身），15m 只跑 smoke 窗口
        h15m_smoke = h15m_full[h15m_full.index >= cutoff]

        print(f"\n▶ {sym}  （1h共{len(h1_full)}根 | 15m冒烟期{len(h15m_smoke)}根）")

        signals = run_signals(sym, h15m_smoke, h1_full, cfg)

        if not signals:
            print("  （该期间无信号产生）")
            continue

        print(f"  共 {len(signals)} 个信号：")
        for s in signals:
            rr = abs(s.tp_price - s.entry_price) / abs(s.entry_price - s.stop_price)
            tag = "▲ 做多" if s.direction == "long" else "▼ 做空"
            print(
                f"  {s.timestamp.strftime('%Y-%m-%d %H:%M')}  {tag}"
                f"  入场={s.entry_price:>10,.2f}"
                f"  止损={s.stop_price:>10,.2f}"
                f"  止盈={s.tp_price:>10,.2f}"
                f"  R:R={rr:.2f}"
            )

    print("\n" + "=" * 65)
    print("冒烟测试完成。如信号数量和方向看起来合理，可进入第③步回测。")


if __name__ == "__main__":
    main()
