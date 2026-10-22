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
| 計分引擎 | 規則計分 (0-100)；累積標籤後改用 LightGBM 模型 |
| 地址圖特徵 | PancakeSwap pair `Swap` 事件 → 同區塊多錢包買入（bundler） |
| 儀表板 | Streamlit |
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
GoPlus + 早期買家 ─────► 風險計分 (0-100)
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

python -m rugguard.main          # 前景執行蒐集程式
```

長期執行（Windows）：登入時自動啟動看門程式，蒐集程式掛掉自動重啟、回補定期接著做，不開視窗。

```powershell
.\scripts\register_task.ps1      # 註冊工作排程「RugGuard」
Start-ScheduledTask -TaskName RugGuard
# 停止：Stop-ScheduledTask -TaskName RugGuard；移除：Unregister-ScheduledTask -TaskName RugGuard
```

紀錄檔：`supervisor.log`、`collector.log`、`backfill.log`（及對應的 `.err.log`）。
電腦睡眠時不會蒐集；要 24 小時不中斷請關閉睡眠或放到不關機的機器。

只評估「剛好一邊是報價幣（WBNB / USDT / BUSD / USDC）」的交易對，另一邊才是新幣（設定在 `rugguard/chains.py`，
之後加其他 EVM 鏈只要新增一筆設定）。每輪從上次掃到的區塊接著掃（不漏交易對）。新交易對會先等 600 塊（BSC 約 0.45 秒/塊 ≈ 4.5 分鐘），
有流動性後才查 GoPlus、統計這 600 塊內的早期買家，並以當下價格作為買入價；約 30 分鐘仍無流動性就放棄。
風險分數 >= 30 推送風險警示，能買分數 >= 50（有模型時）推送能買候選。

## 風險計分規則

| 條件 | 分數 | 說明 |
|---|---|---|
| Honeypot | +30 | 只能買不能賣，最惡意行為 |
| 流動性未鎖 | +20 | `lp_holders` 鎖倉（含黑洞地址）< 50%；GoPlus 無 LP 資料時不計分 |
| 買/賣稅 > 10% | 各 +10 | 隱藏成本陷阱（GoPlus 稅率為 0-1 刻度） |
| Owner 可收回所有權 | +10 | 可竄改合約 |
| Owner 可改持倉 | +10 | 可任意增發 |
| Holder < 100 | +5 | 極少人持倉 |
| Bundler | +10 | 同一區塊 >= 5 個不同錢包買入 |

總分上限 100。等級：SAFE (<30) / WARN (30-59) / HIGH (60-79) / CRITICAL (>=80)

## 測試

```bash
python -m pytest tests/ -v
```

119 個測試，涵蓋計分規則、事件解碼、bundler 特徵、延遲評估、標籤、匯出、模型訓練、價格路徑、回測、儀表板資料。

## 標籤系統（W2）

每個交易對以**評估當下的價格**為買入價，24 小時後回查現價並標記：

| 標籤 | 條件 |
|---|---|
| `dead` | 評估時沒流動性，或價格完全沒動（沒人交易），不進訓練 |
| `rug` | 跌到買入價 10% 以下 |
| `win` | 漲到 2 倍以上（`WIN_RETURN`） |
| `normal` | 其他 |

標籤規則改變時，可用 `rugguard.labeler.relabel_all` 以已存價格重算。
舊版把 USDT/新幣 交易對的 USDT 當成新幣（特徵與價格都錯），`mark_invalid` 會把這類列標成 `invalid`，不進訓練與回測。
這些標籤累積成訓練資料庫，是未來 LightGBM 風險模型的訓練來源。

```bash
# 標籤資料庫預設存於 rugguard.db，自動累積
# 匯出已標籤資料為 CSV 訓練集：
RUGGUARD_EXPORT=1 python -m rugguard.main
# -> 輸出 training_data.csv（每列含 GoPlus + bundler 特徵）
```

每個交易對偵測時會把 GoPlus 安全資料與早期買家特徵一起存進資料庫，
匯出時展開成數值欄位（見 `rugguard/model.py` 的 `FEATURES`）。

## LightGBM 模型

```bash
python -m rugguard.model training_data.csv rugguard_model.txt
# 印出 cross-val AUC，並存檔
```

多分類模型（rug / normal / win），只用有交易的代幣訓練，以**時間外驗證**（walk-forward：用過去訓練、預測未來）評估。
特徵含 GoPlus 安全資料、早期買家 / bundler、觀察窗內 LP 加入 / 撤出、流動性美元深度、前 10 大持有人占比、創建者歷史。
蒐集程式每 7 天自動重訓（`RETRAIN_DAYS`），新模型時間外 win AUC 比現有差 0.02 以上就保留舊的。輸出風險分數 = P(rug)×100、
能買分數 = P(win)×100。`rugguard_model.txt` 存在時 `rugguard.main` 自動使用，否則用規則計分。
新流程（v2）資料滿 200 筆後只用 v2 訓練，避免和舊的「偵測當下」特徵混用。

## 停利回測與 rug 型態

蒐集程式每輪用 Multicall3 對進場 24h 內的交易對取樣價格與兩邊儲備（約 1-2 分鐘一次）。

```bash
python -m rugguard.backtest
```

舊代幣可用 `python -m rugguard.backfill` 回補逐筆價格（bloXroute 公開節點，可中斷續跑）。

輸出各種停利（1.2x-10x）× 停損組合扣手續費與稅後的平均 / 中位報酬與 bootstrap 95% 信賴區間（下界 > 1 才標記 EV>1），
以及 rug 型態：一次崩完（來不及逃）的比例、撤池 vs 倒貨、進場到崩盤的時間、崩盤前曾漲到幾倍。

文獻與業界做法整理見 [docs/research-sota.md](docs/research-sota.md)，階段規劃見 [docs/quant-plan.md](docs/quant-plan.md)。

## 紙上交易

能買分數 >= `MIN_BUY_SCORE` 時開虛擬倉位，每輪用取樣價格判斷停利（`PAPER_TP`，預設 2x）、停損（`PAPER_SL`，預設 0.5x）、
最長持有（`PAPER_MAX_HOURS`，預設 24h），記錄扣手續費與稅後報酬。不動用任何真錢。儀表板顯示持倉、平倉、平均報酬與累積損益。

## 儀表板

```bash
python -m streamlit run rugguard/dashboard.py
```

顯示偵測數、已標籤數、rug 比例、風險等級分布、各等級實際 rug 比例與最新交易對。

## Roadmap

- [x] W1: 新交易對監聽 + 風險計分 + Telegram 警示
- [x] W2: 初始價格快照 + 24h 標籤累積（SQLite + CSV 匯出）
- [x] W2: LightGBM 風險模型（取代規則計分）
- [x] W3: 地址圖特徵（bundler 偵測）— 同區塊多錢包共同買入
- [x] W3: Streamlit 儀表板
- [x] 延遲評估 + 四類標籤 + 多分類模型（能買分數）
- [x] 價格路徑取樣 + 停利/停損回測
- [x] 交易對報價幣判斷修正（USDT/新幣）、鏈設定抽出
- [x] 新特徵：LP 事件、流動性深度、持有人集中度、創建者歷史
- [x] 時間外驗證 + 自動重訓 + 紙上交易 + 看門程式 / 工作排程
- [ ] 回測扣費後期望值為正之前，不做自動下單

## 專案結構

```
rugguard/
├── scanner.py        # 監聽並解碼 PairCreated 事件
├── goplus_client.py  # GoPlus Security API 客戶端
├── bundler.py        # 早期買家 / bundler 特徵（Swap 事件）
├── scoring.py        # 規則計分與分級
├── model.py          # 特徵擷取 + LightGBM 訓練/預測
├── price.py          # pair getReserves 價格
├── store.py          # SQLite 標籤資料庫
├── labeler.py        # 24h 標籤判定與回填
├── export.py         # 訓練集 CSV 匯出
├── chains.py         # 鏈設定（factory、報價幣、出塊時間）
├── paths.py          # Multicall3 價格路徑取樣
├── backfill.py       # 舊代幣逐筆價格回補
├── paper.py          # 紙上交易
├── supervisor.py     # 看門程式（自動重啟）
├── backtest.py       # 停利/停損回測與 rug 型態分析
├── dashboard.py      # Streamlit 儀表板
├── notifier.py       # Telegram 推播 + 訊息格式化
└── main.py           # 主流程整合
tests/                # pytest 測試
```
