# RugGuard — 鏈上新代幣 Rug 風險偵測

> 一個自動化的「新代幣安全哨兵」：即時監聽 PancakeSwap (BSC) 新上線的交易對，分析代幣安全特徵，對高風險代幣推送 Telegram 警示。

## 這個專案解決什麼問題

加密貨幣新代幣市場詐騙頻傳——honeypot（只能買不能賣）、拉高倒貨（rug pull）、隱藏高稅、未鎖流動性。**每分鐘都有新的騙局代幣上線**，散戶無法逐一人工檢查。

RugGuard 把「代幣上線前的安全檢查」變成自動化流程：從鏈上捕捉新交易對、查詢安全特徵、計算風險分數、即時警示。**你不必會看鏈上資料，也會被保護。**

## 技術棧

| 層 | 工具 |
|---|---|
| 鏈上資料 | web3.py + PancakeSwap Factory `PairCreated` 事件 |
| 安全資料 | GoPlus Security API |
| 計分引擎 | 自訂規則計分 (0-100) + 風險分級 |
| 推播 | Telegram Bot API |
| 品質 | pytest 測試驅動開發 |

## 架構

```
PancakeSwap Factory (BSC)
        │  PairCreated 事件 (web3.py eth_getLogs)
        ▼
  新交易對 (token0/token1/pair)
        │
        ▼
GoPlus Security API ───► 風險計分 (0-100)
  安全特徵特徵             + 風險等級
   (honeypot/tax/            SAFE / WARN
    liquidity/owner)          HIGH / CRITICAL
        │
        ▼
  Telegram 警示 (分數 ≥ 30)
```

## 快速開始

```bash
pip install -r requirements.txt
cp .env.example .env
# 填入 BSC_RPC_URL、TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID

python -m rugguard.main
```

每 60 秒掃描最新 100 個區塊的新交易對，風險分數 >= 30 即推送。

## 風險計分規則

| 條件 | 分數 | 說明 |
|---|---|---|
| Honeypot | +30 | 只能買不能賣，最惡意行為 |
| 流動性未鎖 | +20 | 隨時可抽走，rug pull 主因 |
| 買/賣稅 > 10% | 各 +10 | 隱藏成本陷阱 |
| Owner 可收回所有權 | +10 | 可竄改合約 |
| Owner 可改持倉 | +10 | 可任意增發 |
| Holder < 100 | +5 | 極少人持倉 |

等級：SAFE (<30) / WARN (30-59) / HIGH (60-79) / CRITICAL (>=80)

## 測試

```bash
python -m pytest tests/ -v
```

16 個測試，涵蓋計分規則、事件解碼、API 回應解析、訊息格式化。全程 TDD 開發。

## 標籤系統（W2）

每個偵測到的交易對會在**上線當下快照初始價格**（無需 archive node），
24 小時後回來查現價，跌超過 90% 標記為 `rug`，否則標記 `normal`。
這些標籤累積成訓練資料庫，是未來 LightGBM 風險模型的訓練來源。

```bash
# 標籤資料庫預設存於 rugguard.db，自動累積
# 匯出已標籤資料為 CSV 訓練集：
RUGGUARD_EXPORT=1 python -m rugguard.main
# -> 輸出 training_data.csv
```

## Roadmap

- [x] W1: 新交易對監聽 + 風險計分 + Telegram 警示
- [x] W2: 初始價格快照 + 24h 標籤累積（SQLite + CSV 匯出）
- [ ] W2: LightGBM 風險模型（取代規則計分）
- [ ] W3: 地址圖特徵（bundler 偵測）— 多錢包短時間共同買入的聚類分析
- [ ] W3: Streamlit 儀表板

## 專案結構

```
rugguard/
├── scanner.py        # 監聽並解碼 PairCreated 事件
├── goplus_client.py  # GoPlus Security API 客戶端
├── scoring.py        # 風險計分與分級
├── notifier.py       # Telegram 推播 + 訊息格式化
└── main.py           # 主流程整合
tests/                # pytest 測試
```
