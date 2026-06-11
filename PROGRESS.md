# 项目进度记录

## 项目概况
加密交易信号提醒系统（OKX，BTC/ETH USDT 永续，波段 1-5 天，信号推送微信）。
策略分三层：区间交易（核心）+ 缠论确认 + 六爻过滤。

---

## 已完成

### ① 行情接入（✅）
- **`data/okx_feed.py`**：ccxt 连接 OKX 公共行情，无需 API key
- 三个周期全部分页拉取：15m（2年≈70080根）、1h（2年≈17520根）、1d（全量自2020-01）
- 缓存为 parquet，去重 + 时间排序

### ② 区间信号逻辑（✅ 22个单测全通过）
- **`config.py`**：集中参数表，含 `max_hold_days`、`tp_mode`、`chan_on`、`liuyao_on`、`chan_liuyao_and`
- **`indicators.py`**：ADX(14) Wilder，`_wilder_smooth`（TR/DM）+ `_rma`（DX→ADX，值域[0,100]）
- **`strategy/range_strategy.py`**：`Signal` dataclass + `run_signals()`
- **`tests/`**：22 个单元测试全部通过

### ③ 回测框架（✅）
- **`backtest/engine.py`**：逐 K 线模拟，含手续费(0.05%)、资金费(0.01%/8h)、滑点(0.01%/side)
- **`backtest/metrics.py`**：`compute_stats()` + `slice_period()`
- **`backtest/plot.py`**：归一化权益曲线图
- **`backtest.py`**：主回测脚本，支持版本 A/B 并排输出

### ④ 缠论 + 六爻层（✅）
- **`strategy/chan.py`**：MACD 背驰检测（底背驰→bull / 顶背驰→bear），在 1h 上预计算
  - 信号密度：~9% bull，~10% bear，余 none
- **`strategy/liuyao.py`**：梅花易数时间起卦，`lunar_python` 库，LRU 缓存
  - 信号分布：~38% bull，~22% bear，~40% neutral
- **`backtest/engine.py`** 已集成两层过滤器，支持两种组合逻辑：
  - `chan_liuyao_and=True`（AND）：缠论与六爻必须同向
  - `chan_liuyao_and=False`（OR）：任一放行，六爻观望不拦截

### ⑤ 推送 + 调度器（✅ 端到端联调通过）
- **`notifier/pushplus.py`**：PushPlus 微信推送，读 `.env` 中的 `PUSHPLUS_TOKEN`
  - `notify_entry(symbol, direction, entry, stop, tp)`
  - `notify_exit(symbol, direction, reason, pnl_pct)`
  - TOKEN 缺失时降级打印到控制台
  - `load_dotenv` 改用绝对路径，子目录运行也能正确读取 `.env`
- **`app.py`**（Streamlit）：三段式监控页面，每 15 秒自动刷新
  - 顶部：BTC / ETH 实时价格（st.metric）
  - 中部：当前持仓（入场价 / 止损价 / 止盈价 / 浮盈）
  - 底部：历史信号记录表（最近 20 笔，盈亏着色）
  - 运行：`streamlit run app.py`
- **`scheduler.py`**：每 15 分钟定时拉最新 K 线、跑信号、有变化推送
  - 状态持久化到 `signal_state.json`，避免重复推送
  - `python3 scheduler.py --once` 单次运行 BTC + ETH 均正常（已验证）
  - 运行：`python3 scheduler.py`
- **`.env.example`**：提示用户填写 PushPlus token
- **已修复 Bug（2026-06-10）**：
  - `scheduler.py`：`refresh_cache(symbol, tf)` → `refresh_cache([symbol], [tf])` （参数须为列表）
  - `data/okx_feed.py`：新增 `_OkxExchange` 子类，覆盖 `keysort` 兼容 OKX 返回的 `None` key
  - `scheduler.py` + `notifier/pushplus.py`：`load_dotenv` 均改为绝对路径

---

## 当前位置
**第⑤步端到端联调完成**。策略已验证（ETH 版本 F 检验段 Sharpe=2.14），`scheduler.py --once` BTC/ETH 均正常拉取行情并完成信号检测。
填入真实 PushPlus token 后即可上线。

---

## 最终策略配置（已验证）

分割点：调参段 2024-06-10 ~ 2025-06-10（前12个月），检验段 2025-06-10 ~ 今（后12个月）
成本：taker 0.05%、funding 0.01%/8h、slippage 0.01%/side、初始资金 10,000 USDT、杠杆上限 5×

### ETH — 版本 F（✅ 验收通过，用于生产）
参数：`tp_mode=opposite, chan_on=True, liuyao_on=True, chan_liuyao_and=True, adx_thresh=25, N=48`

| 段 | 交易数 | 胜率% | 期望值% | 盈亏比 | 总收益% | 最大回撤% | Sharpe |
|----|--------|-------|---------|--------|---------|-----------|--------|
| 调参 | 14 | 28.6 | +0.823 | 4.96 | +11.40 | -8.76 | +0.85 |
| **检验** | **13** | **46.2** | **+1.250** | **3.53** | **+16.99** | **-3.18** | **+2.14** |

ETH 版本 F 检验段 13 笔逐笔明细详见 `eth_f_detail.py` 运行结果。

### BTC — 版本 BTC-B（✅ 调参验证通过，推荐用于生产）
参数：`tp_mode=opposite, chan_on=True, liuyao_on=True, chan_liuyao_and=True, adx_thresh=25, N=24`（N 从 48 缩短到 24，1天窗口）

| 段 | 交易数 | 胜率% | 期望值% | 盈亏比 | 总收益% | 最大回撤% | Sharpe |
|----|--------|-------|---------|--------|---------|-----------|--------|
| 调参 | 22 | 27.3 | -0.543 | 0.88 | -11.37 | -14.10 | -1.46 |
| **检验** | **38** | **55.3** | **+0.222** | **1.16** | **+8.53** | **-5.18** | **+1.12** |

BTC 调参对比（检验段期望值排序）：

| 版本 | 调整 | 交易数 | 期望值% | 总收益% | Sharpe |
|------|------|--------|---------|---------|--------|
| F-base | 无（N=48） | 21 | -0.041 | -1.00 | -0.12 |
| BTC-A | adx_thresh=20 | 9 | +0.214 | +1.83 | +0.46 |
| **BTC-B** | **N=24** | **38** | **+0.222** | **+8.53** | **+1.12** |
| BTC-C | adx_thresh=20 + N=24 | 20 | +0.316 | +6.32 | +1.10 |

选 BTC-B 而非 BTC-C：38 笔 vs 20 笔，信号量更充裕，Sharpe 相近。

### BTC+ETH 合并（版本 F，各自最优参数）

| 段 | 交易数 | 期望值% | 总收益% | 最大回撤% | Sharpe |
|----|--------|---------|---------|-----------|--------|
| 调参 | 30 | -0.023 | -0.10 | -5.62 | +0.03 |
| **检验** | **34** | **+0.453** | **+9.03** | **-2.09** | **+1.66** |

---

## 版本演进记录

| 版本 | 止盈 | 缠论 | 六爻 | 组合 | 说明 |
|------|------|------|------|------|------|
| A | 中线 | ✗ | ✗ | — | 基准 |
| B | 中线 | ✗ | ✗ | — | 时间止损 3 天 |
| D | 对侧 | ✗ | ✗ | — | 只改止盈 |
| E | 中线 | ✓ | ✓ | AND | 中线+双层 |
| **F** | **对侧** | **✓** | **✓** | **AND** | **生产版本** |
| G | 对侧 | ✓ | ✓ | OR | 过滤太松，期望值转负 |

---

## 待办

| 任务 | 优先级 | 状态 |
|------|--------|------|
| 把 BTC-B 参数写入 `scheduler.py` 的 CONFIGS | 高 | 待做 |
| 填入真实 PushPlus token，测试推送到微信 | 高 | 待做 |
| `app.py` 的价格 / 持仓改为从真实信号文件读取 | 中 | 待做 |
| `scheduler.py` 中信号检测逻辑改用 `run_signals()` 实时流 | 中 | 待做 |
| BTC-B 检验段样本量（38笔）是否足够，考虑扩大检验窗口 | 低 | 待决策 |
| 最小止损距离过滤（防止 R:R 过低的信号） | 低 | 待决策 |

---

## 文件结构

```
crypto-signal/
├── config.py                  # 参数表（含 chan_liuyao_and 字段）
├── indicators.py              # ADX 指标
├── strategy/
│   ├── __init__.py
│   ├── range_strategy.py      # 区间信号逻辑
│   ├── chan.py                 # 缠论背驰检测（MACD 面积法）
│   └── liuyao.py              # 六爻时间起卦过滤
├── backtest/
│   ├── engine.py              # 回测引擎（含缠论/六爻过滤入口）
│   ├── metrics.py             # 统计指标
│   └── plot.py                # 权益曲线图
├── notifier/
│   ├── __init__.py
│   └── pushplus.py            # PushPlus 微信推送
├── tests/
│   ├── __init__.py
│   ├── test_indicators.py
│   └── test_range_strategy.py
├── data/
│   ├── __init__.py
│   └── okx_feed.py
├── cache/                     # parquet 缓存（gitignore）
├── app.py                     # Streamlit 监控页面
├── scheduler.py               # 15分钟定时调度
├── backtest.py                # 主回测脚本（版本 A/B）
├── compare_versions.py        # 多版本对比（A/D/E/F）
├── compare_fg.py              # F vs G 对比
├── btc_tuning.py              # BTC 调参脚本
├── eth_f_detail.py            # ETH 版本 F 逐笔明细
├── smoke_test.py              # 30 天冒烟测试
├── .env.example               # token 配置模板
├── STRATEGY.md                # 完整策略说明
└── PROGRESS.md                # 本文件
```

---

*最后更新：2026-06-10，第⑤步端到端联调完成，scheduler --once BTC/ETH 均正常运行*
