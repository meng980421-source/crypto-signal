# Crypto Signal Monitor

OKX BTC/ETH 永续合约区间交易信号系统，微信推送 + Streamlit 监控面板。

---

## 快速启动

```bash
pip install -r requirements.txt
cp .env.example .env         # 填写 PUSHPLUS_TOKEN
python scheduler.py          # 本地持续运行（每 15 分钟检测一次）
streamlit run app.py         # 监控页面（http://localhost:8501）
```

---

## 部署到 GitHub Actions（推荐：免费定时推送）

### 第一步：把代码推到 GitHub

```bash
cd /path/to/crypto-signal
git init
git add .
git commit -m "init"
# 在 GitHub 建好仓库后：
git remote add origin https://github.com/你的用户名/crypto-signal.git
git branch -M main
git push -u origin main
```

### 第二步：复制 workflow 文件

```bash
mkdir -p .github/workflows
cp deploy/github_actions.yml .github/workflows/scheduler.yml
git add .github/
git commit -m "add github actions scheduler"
git push
```

### 第三步：配置 PushPlus Token（GitHub Secret）

1. 打开你的 GitHub 仓库页面
2. 进入 **Settings → Secrets and variables → Actions**
3. 点击 **New repository secret**
4. Name 填 `PUSHPLUS_TOKEN`，Secret 填你的 PushPlus token
5. 点击 **Add secret**

> PushPlus token 获取：前往 [pushplus.plus](https://www.pushplus.plus)，微信扫码登录后在首页复制 token。

完成后 GitHub Actions 每 15 分钟会自动运行，有信号就推送到微信。

---

## 部署到 Railway（备用：Streamlit 24 小时在线）

1. 注册 [railway.app](https://railway.app)，新建 Project → Deploy from GitHub Repo
2. 选择你的 `crypto-signal` 仓库
3. Railway 会自动读取 `deploy/railway.toml` 的启动命令
4. 在 Railway 项目的 **Variables** 面板添加 `PUSHPLUS_TOKEN=你的token`
5. 部署完成后访问 Railway 给出的公网 URL 即可

---

## 策略说明

| 参数 | ETH (版本F) | BTC (BTC-B) |
|------|------------|-------------|
| 区间窗口 N | 48（2天） | 24（1天） |
| ADX 阈值 | 25 | 25 |
| 止盈模式 | opposite | opposite |
| 缠论过滤 | ✓ | ✓ |
| 六爻过滤 | ✓ | ✓ |
| 组合模式 | AND | AND |

检验段（2025-06-10 至今）：
- ETH：13笔，胜率46%，期望值+1.25%/笔，Sharpe=2.14
- BTC：38笔，胜率55%，期望值+0.22%/笔，Sharpe=1.12

---

## 文件结构

```
crypto-signal/
├── config.py            # 参数（ETH_LIVE / BTC_LIVE）
├── scheduler.py         # 定时信号检测（--once 单次模式）
├── app.py               # Streamlit 监控面板
├── requirements.txt     # 依赖
├── .env.example         # token 模板
├── signal_state.json    # 运行时状态（自动生成）
├── deploy/
│   ├── github_actions.yml   # GitHub Actions workflow 源文件
│   └── railway.toml         # Railway 部署配置
├── strategy/
│   ├── range_strategy.py    # 区间信号
│   ├── chan.py              # 缠论背驰
│   └── liuyao.py           # 六爻过滤
├── backtest/
│   ├── engine.py
│   ├── metrics.py
│   └── plot.py
├── notifier/
│   └── pushplus.py
└── data/
    └── okx_feed.py
```
