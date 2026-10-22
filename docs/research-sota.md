# RugGuard 研究筆記：rug pull 偵測與 memecoin 交易的現況（2026-10）

> 範圍：學術 rug／scam token 偵測、適合小型表格資料的模型、業界工具、memecoin 報酬與狙擊機器人，最後給 RugGuard 的建議。
> 引用都查過 arXiv 摘要頁或出版頁。「未驗證」代表只看到二手摘要。

## 1. 學術研究一覽

| 論文 | 方法 | 特徵 | 資料量 | 報告指標 | 能否在 rug 前預警 |
|---|---|---|---|---|---|
| Xia et al., *Trade or Trick?*（SIGMETRICS 2022） | 關聯推論（guilt-by-association）＋ ML | 池子流動性、交易、合約特徵 | Uniswap 上找到 >10K 個 scam token、>40K 個共謀地址 | 估計約 50% 的 token 是 scam | 大致是事後辨識 |
| Cernera et al., *Token Spammers, Rug Pulls, and Sniper Bots*（USENIX Sec 2023） | 規則／量測研究 | token 壽命、建立者、LP 加入與移除、狙擊機器人 | BSC 1,078,016 個 token、ETH 323,863 個 | BSC 有 59.2% 的 token 活不到 1 天；有池子的 1-day token 中 81.2% 符合 rug 模式；1-day rug 獲利約 $240M | 量測研究，不是預測模型 |
| Mazorra et al., *Do not rug on me*（Mathematics 2022） | XGBoost、FT-Transformer | 合約啟發式特徵、token 擴散 | 約 27,588 個 Uniswap token | Acc 0.99、Recall 0.954、Precision 0.984 | 號稱在惡意動作前；後續論文指出可能有 post-scam 資訊洩漏 |
| CRPWarner（arXiv 2403.01425，TSE） | 規則：bytecode → CFG → Datalog | 合約後門（mint、改餘額、隱藏 owner 等） | 69 份標註合約＋13,484 份合約 | P 91.8% / R 85.9% / F1 88.7% | 可以，部署當下就能掃。只抓合約型 rug，抓不到交易型 rug（直接撤 LP） |
| RPHunter（arXiv 2506.18398） | GNN（程式碼風險圖＋token 流動圖）＋ attention 融合 | 合約語意與轉帳行為圖 | 645 起人工標註事件 | P 95.3% / R 93.8% / F1 94.5%；實戰掃 4,801 個 token，precision 約 90% | 需要累積一段轉帳資料；LROO 批評它的標註定義不一致 |
| HNN4RP（JEIT 2025，中文期刊） | 異質 GNN＋BiLSTM | 帳戶與合約的異質交易圖 | 3 個 ETH 資料集 | F1 0.85–0.95；作為 baseline 的 LightGBM F1 約 0.67–0.72 | 不明 |
| SoK（arXiv 2403.16082，ISSTA 2025） | 綜述 | 34 種 rug 成因 | 2,360 個實例 | 14 種工具合計涵蓋 73.5% 的成因；fake LP lock、hidden fee、wash trading 無人涵蓋 | — |
| Yaremus et al., TON（arXiv 2509.01168） | Gradient Boosting | DEX 早期交易特徵 | STON.fi 與 DeDust | AUC 最高 0.891（以 TVL 定義 rug） | 可以，只用上線後前 5 分鐘的資料 |
| *Catching the Rug*（arXiv 2608.20271，Solana／pump.fun） | XGBoost 表現最好 | 流動性與社群動態，不用程式碼特徵 | 約 640 萬個 token | 摘要頁沒有給數字 | 可以，只用前 5 分鐘預測 1 小時內是否 rug |
| TM-RugPull（arXiv 2602.21529）／LROO（arXiv 2603.11324） | TabPFN；特徵嚴格只取 rug 之前 | 鏈上資料＋合約資訊＋OSINT（社群、搜尋熱度） | 1,000 個人工標註專案 | 摘要頁沒有給數字；重點是批評既有資料集有時間洩漏 | 有，特徵只取撤池之前 |
| SolRugDetector（arXiv 2603.24625） | 行為規則＋人工驗證 | freeze authority 濫用、撤 LP、pump-and-dump | Solana 100,063 個 token，其中 76,469 個被標為 rug | 抽樣驗證 FP 率 0.26% | 論文指出生命週期「極短」 |
| Mongardini & Mei, *A Midsummer Meme's Dream*（arXiv 2507.01963） | 量測研究 | wash trading、LP 價格灌水（LPI） | 4 條鏈共 34,988 個 meme token | 報酬 >100% 的 token 中，82.8% 有人為拉抬的跡象 | — |
| *Meme Coin Factories*（arXiv 2609.10246，CCS'26） | 量測研究 | wash trading、隱藏創建者、協同賣出、copycat | pump.fun 全部約 1,500 萬個 coin | 發現操縱已經服務化（MMaaS） | — |

LLM 方面：沒有找到經同儕審查、專門用 LLM 偵測 rug pull 的論文。現有 LLM 研究（例如 SCALM, arXiv 2502.04347）處理的是一般合約漏洞。arXiv 2608.01609 *From Viral to Void* 未驗證是否使用 LLM。

**小結**：
- 文獻裡 0.95 以上的分數，多半來自「rug 後再分類」或可能有時間洩漏的設定。
- 真正「上線前 5 分鐘就預測」的研究（TON、Solana），用的都是 gradient boosting。可驗證的 AUC 約 0.89。
- RugGuard 在只看有交易的 token 時 AUC 0.72，代表還有改進空間，但方向沒有錯。

## 2. 模型怎麼選
- Grinsztajn et al.（NeurIPS 2022）比較 45 個資料集，在約 1 萬筆以內的中型表格資料上，樹模型（XGBoost、RF）仍優於深度學習。
- Shwartz-Ziv & Armon（Information Fusion 2022）的結論也一樣：XGBoost 勝過那些號稱表格 SOTA 的深度模型，而且調參成本低很多。
- TabPFN（Hollmann et al., *Nature* 2025）在 1 萬筆以內的資料上贏過調參 4 小時的強 baseline 集成。RugGuard 目前約 500 筆有交易的資料，值得拿它當第二個 baseline。
- GNN 適合資料量大、而且有完整轉帳圖的情境。在 RugGuard 目前的規模，比較好的做法是把圖的資訊壓成表格特徵（叢集數、資金來源集中度），再交給 GBDT。

**結論：繼續用 LightGBM，再加 TabPFN 對照。現階段不要上深度學習或 GNN。**

## 3. 業界工具看哪些訊號
- **GoPlus**：靜態與模擬旗標，例如 is_honeypot、buy/sell_tax、owner_change_balance、hidden_owner、holders。RugGuard 已經在用。注意欄位值是字串，而且缺值不等於安全。
- **honeypot.is**：檢查能不能賣出，並回報稅率與 gas。官方文件沒有寫明方法，一般認知是模擬買賣（未驗證）。
- **Token Sniffer**（Solidus Labs）：把一組 pass/fail 檢查彙總成 0–100 分，其中包含與已知 scam 合約的相似度。官方沒有公開權重。
- **Bubblemaps**：把持有者畫成泡泡，用鏈上轉帳把地址連成叢集。另有 bundle（同一個區塊或上線幾秒內買入）和 Time Node（同一時間獲得資金或開始活動的錢包）。
- **DexScreener／GMGN／Birdeye**：價量、持有者、開發者錢包與 sniper／insider 標記。沒有找到這些平台的一手方法文件，這裡只列用途。

## 4. 報酬分佈、rug 速度、狙擊機器人
- **rug 的速度**：Cernera 研究中，BSC 範例 token 在建池約 2 小時（約 2,350 個區塊）後撤池。頭號 token spammer 的 token 壽命中位數只有 45 分鐘。Solana 的研究也說生命週期極短。
- **RugGuard 目前的觀察窗**：600 個區塊（約 4.5 分鐘）可以接受，學術上也是用前 5 分鐘。但這代表 rug 不一定會等你。
- **狙擊機器人**：在 BSC 的 rug 池中，130 個狙擊地址出現在 68.7% 的池子，其中約 31% 的交換發生在加入流動性的同一個區塊。Cernera 推測它們常常也是受害者，但沒有量化盈虧。
- **狙擊的淨效果**：arXiv 2601.08641 認為 bot 主要是把利潤從慢的散戶轉移給早進場的人。
- **夾子攻擊**：Dune 單日資料顯示，BSC 有 35.5% 的區塊含 sandwich 攻擊（新聞與 dashboard 數據，非同儕審查）。
- **翻倍的幣也不可靠**：報酬 >100% 的 meme token 中有 82.8% 有人為拉抬（Mongardini & Mei）。你看到的 2x 很可能就是出貨前的拉盤。
- **止盈倍數**：沒有找到經同儕審查、針對 memecoin 最佳止盈倍數的研究。這必須用自己的資料回測，不能套用網路上的說法。

## 5. 給 RugGuard 的建議
**要加的特徵（依投入產出排序）**
1. 建立者錢包歷史：過去部署過幾個 token、其中幾個 rug（連環 rugger）。這是 Cernera 所說 token spammer 的核心訊號。
2. 早期買家的資金來源叢集：前 N 個買家是否由同一個地址或同一個 CEX 提領批次供應 gas 或 BNB（Bubblemaps 的作法）。
3. LP 事件：加入流動性的金額、LP token 是否 burn 或鎖倉（注意假鎖倉）、在觀察窗內有沒有移除。
4. 持有者集中度：前 10 名占比、Gini。要排除 LP 和 dead 地址。
5. bytecode 相似度：與已知 rug 合約比對 opcode hash 或 MinHash（Token Sniffer 的想法），或加上 CRPWarner 類的後門規則。
6. 建立者在觀察窗內的賣出量，以及同一個區塊內自己買賣的情形。

**評估方式**
- 只用時間切分（walk-forward）。特徵一律取建池後 600 個區塊內的資料，避免 TM-RugPull 指出的時間洩漏。
- 看 precision@top-k 和校準度（Brier 分數、reliability 圖），不要只看 AUC。
- 回測規則：每筆交易扣買賣稅（GoPlus 的 tax）、滑價（依池子深度計算）、gas、被夾的成本；進場價用你實際能拿到的區塊，不是建池價。
- 掃一組止盈倍數（1.3x、1.5x、2x、3x）加上時間停損，算期望值與最大回撤；同時把「賣不出去」和「撤池瞬間歸零」算進去。

**誠實評估**
- 有交易的 token 中約 87% 會 rug，10% 翻倍。若翻倍時賺 1 倍、rug 時虧掉全部，隨機買的期望值約為 0.10×1 − 0.87×1 ≈ −0.77。
- 就算模型把 top-k 中翻倍的比例拉到 30%，扣掉稅、滑價和夾子之後仍很可能是負的，除非 rug 的損失能用時間停損控制住。
- 學術證據一致顯示利潤集中在創建者、狙擊者和最早出場的人，而大多數翻倍是人為拉抬。
- 因此建議 RugGuard 的主要用途是避雷（風險過濾、加入黑名單），把「找幣買」當成必須先用回測證明期望值為正的假說。自動下單應等 walk-forward 回測在扣費後仍為正之後再做，並先用極小金額實盤驗證。

## 來源
- Xia et al. Trade or Trick? https://arxiv.org/abs/2109.00229
- Cernera et al. USENIX Sec 2023 https://www.usenix.org/conference/usenixsecurity23/presentation/cernera ； https://arxiv.org/html/2206.08202v3
- Mazorra et al. Do not rug on me https://arxiv.org/abs/2201.07220 ； https://ideas.repec.org/a/gam/jmathe/v10y2022i6p949-d772354.html
- CRPWarner https://arxiv.org/abs/2403.01425
- RPHunter https://arxiv.org/abs/2506.18398v2
- HNN4RP https://jeit.ac.cn/article/doi/10.11999/JEIT250160
- SoK Rug Pull https://arxiv.org/abs/2403.16082
- TON rug detection https://arxiv.org/abs/2509.01168
- Catching the Rug (Solana) https://arxiv.org/abs/2608.20271
- TM-RugPull https://arxiv.org/abs/2602.21529 ； LROO https://arxiv.org/abs/2603.11324
- SolRugDetector https://arxiv.org/abs/2603.24625
- A Midsummer Meme's Dream https://arxiv.org/abs/2507.01963
- Meme Coin Factories https://arxiv.org/abs/2609.10246
- Meme coin copy trading / bots https://arxiv.org/pdf/2601.08641
- SCALM（LLM 合約分析）https://arxiv.org/abs/2502.04347
- Grinsztajn et al. NeurIPS 2022 https://arxiv.org/abs/2207.08815
- Shwartz-Ziv & Armon https://arxiv.org/abs/2106.03253
- TabPFN, Nature 2025 https://pubmed.ncbi.nlm.nih.gov/39780007/
- GoPlus docs https://docs.gopluslabs.io/ ；honeypot.is https://docs.honeypot.is/
- Token Sniffer API（Decrypt）https://decrypt.co/123042
- Bubblemaps https://wiki.bubblemaps.io/bubblemaps-v2/how-does-it-work ； https://blog.bubblemaps.io/how-to-analyze-meme-coin-holders-with-bubblemaps/
- BSC sandwich（Decrypt／Dune）https://decrypt.co/294648 ；BNB Chain https://www.bnbchain.org/en/blog/what-are-sandwich-attacks
