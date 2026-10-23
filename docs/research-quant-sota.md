# 加密貨幣量化：學界與業界現況（SOTA）對照研究

日期：2026-10-23。
標記說明：「已開啟」表示我實際打開該頁面並讀到摘要。「僅搜尋摘要」表示只看到搜尋結果的描述，未讀全文。「未驗證」表示無法確認。
限制：我只讀到摘要頁，沒有讀到各論文的全文表格。所以樣本期、成本細節多半標「摘要未載」。

## 結論先講

1. 沒有證據顯示小資金散戶有「可靠的 edge」。
2. 趨勢跟隨（時間序列動能）是證據最強的一項。但它的好處主要是降低回撤，不是保證更高夏普。這與你的結果一致。
3. 資金費率套利的報酬已大幅縮水。這也與文獻方向一致。
4. 新幣、LP、MEV 這類領域，文獻都指出：散戶是被拿錢的一方。
5. 機器學習預測，扣掉成本後沒有可靠勝出的證據。

## 1. 動量與趨勢跟隨

| 文獻 | 方法 / 樣本 | 報告結果 | 扣成本？ | 近年是否變弱 |
|---|---|---|---|---|
| Liu & Tsyvinski, *Risks and Returns of Cryptocurrency*（NBER w24877，2018；RFS 2021） | BTC、XRP、ETH；時間序列動能與投資人關注度 | 加密貨幣報酬可被動量與關注度預測，與股票、總經因子關係低 | 摘要未載 | 摘要未載。樣本很早期（未驗證確切期間） |
| Liu, Tsyvinski & Wu, *Common Risk Factors in Cryptocurrency*（NBER w25882；Journal of Finance 77(2), 1133-1177, 2022） | 橫斷面；市場、規模、動量三因子 | 三因子模型解釋橫斷面報酬 | 摘要未載 | 摘要未載 |
| Fieberg 等 5 人，*A Trend Factor for the Cross-Section of Cryptocurrency Returns*（JFQA 60(7), 2025） | 超過 3,000 個幣；用機器學習合成多週期技術指標，稱 CTREND | 作者稱訊號可預測報酬、不被已知因子解釋 | 作者稱「扣成本後仍存在」，但本次沒讀到數字 | 作者稱各子期穩健。我沒有獨立驗證 |
| Han, Kang & Ryu，*Time-Series and Cross-Sectional Momentum in the Cryptocurrency Market: A Comprehensive Analysis under Realistic Assumptions*（工作論文） | 納入交易成本與每日價格波動（強平） | 時間序列動能證據強。橫斷面動能證據弱。許多顯著的動能組合在現實假設下被強平或不顯著 | 有納入 | 僅搜尋摘要；全文 403，**未驗證細節** |
| Zarattini, Pagani & Barbon，*Catching Crypto Trends*（Swiss Finance Institute RP 25-80，2025） | Donchian 通道集成 + 波動率部位；前 20 大流動幣輪動 | 作者稱扣費後夏普 > 1.5，相對 BTC 年化 alpha 10.8% | 作者稱已扣費 | 樣本含 2015 起的早期高報酬期；沒有獨立複製。QuantifiedStrategies 明說未回測驗證 |
| Rozario 等，*A Decade of Evidence of Trend Following Investing in Cryptocurrencies*（arXiv 2009.12155，2020） | 趨勢跟隨，十年資料 | 稱「255% walkforward 年化報酬」 | 摘要未載 | 數字極端，我視為不可信的行銷式結果（判斷，非查證） |
| Hudson & Urquhart（Annals of Operations Research，2019） | 約 15,000 條技術規則，多重檢定修正 | 多數幣有可預測性；BTC 在樣本外期間無可預測性 | 僅搜尋摘要 | 僅搜尋摘要，未開啟全文 |

觀察：

- 「時間序列動能有效、橫斷面動能較弱」是 Han 等的結論。這和你只做 BTC/ETH 的長/空倉做法一致。（僅搜尋摘要）
- 多數正面論文的樣本含 2014-2021 年。那段期間加密貨幣整體暴漲。你的樣本外是 2023 年起，結果較弱並不意外。
- 「發表後是否衰退」：我沒有找到直接檢驗加密貨幣動能發表後衰退的已驗證論文。**未驗證**。
- 動量與趨勢報酬很依賴行情。這點你已經自己發現。

## 2. 套利與資金費率

| 文獻 | 內容 | 與你的結果 |
|---|---|---|
| Schmeling, Schrimpf & Todorov, *Crypto carry*（BIS Working Paper 1087，2023-04-04，已開啟） | BTC、ETH 的現貨多+期貨空。平均 carry 高於 10%/年，最高到 60%。原因是小額散戶追漲的槓桿需求，加上套利資金有限。套利者面臨保證金暴漲與下跌時的強平風險 | 你的 2020-2021 年 17-48% 與此一致。BIS 也警告尾端風險 |
| He, Manela, Ross & von Wachter, *Fundamentals of Perpetual Futures*（arXiv 2212.06888，已開啟） | 永續合約無套利價格。偏離「隨時間縮小」。隱含的套利策略夏普很高 | 與你「後期報酬下降」方向一致。注意：夏普高不等於扣成本後高報酬。發表期刊未驗證 |
| Ackerer, Hugonnier & Jermann, *Perpetual Futures Pricing*（arXiv 2310.11771，已開啟；Mathematical Finance 36(3)，2025，僅搜尋摘要） | 純定價理論：永續價格是現貨在隨機時點的風險中性期望 | 理論框架，不提供實際報酬衰退證據 |

- 佐證資金費率正常化的資料只有交易所新聞稿（BitMEX 稱極端資金費率減少 90%）。那是利益相關方，我只當參考，不算高可信。
- 我沒有找到已驗證的同儕審查論文，直接量化「2023 年後 carry 衰退到 1-3%」。你的實測是唯一的直接證據。**未驗證**。
- 結論：套利資金增加後，carry 被壓縮是合理的經濟推論。你算出的 3.2% 與穩定幣收益相當，無需意外。

## 3. 機器學習與過擬合

**機器學習結果：**

- Jaquart, Dann & Weinhardt（*J. of Finance and Data Science* 7, 2021，已開啟）：1 到 60 分鐘預測，模型勝過隨機。多空策略扣成本前月報酬最高 39%。**扣成本後虧損**。
- Jaquart, Köpke & Weinhardt（同刊 2022，僅搜尋摘要）：前 100 大幣每日漲跌，平均準確率 52.9%-54.1%。這個優勢很薄。
- Fieberg 等的 CTREND 是少數用 ML 且發表在頂級期刊的正面證據。但它合成的是技術指標，且是橫斷面多空組合，小資金難複製。（判斷）
- 本次未找到「深度學習穩定勝過簡單基準」的已驗證證據。

**過擬合與多重檢定（皆已開啟）：**

- Bailey, Borwein, López de Prado & Zhu, *The Probability of Backtest Overfitting*（J. of Computational Finance 20(4), 2017）：用 CSCV 估計過擬合機率。主張留出樣本法在回測中不可靠。
- Bailey & López de Prado, *The Deflated Sharpe Ratio*（J. of Portfolio Management 40(5), 2014；SSRN 2460551，僅搜尋摘要）：校正多次嘗試造成的選擇偏誤與非常態。
- Harvey, Liu & Zhu, *...and the Cross-Section of Expected Returns*（NBER w20592；RFS 29(1), 2016，已開啟 NBER 頁）：新因子應要求 t 值大於約 3.0。多數宣稱的發現可能是假的。

對你的意義：你試了四個想法、多組均線與動能參數。這些都該算作「嘗試次數」。你的 Sharpe 差異 95% 信賴區間含 0，這正是這些文獻預期的樣子。

## 4. 微結構：誰賺錢

- Cernera, La Morgia, Mei & Sassi, *Token Spammers, Rug Pulls, and Sniper Bots*（USENIX Security 2023，已開啟）：約 60% 的代幣活不到一天。1% 的地址創造 20%-25% 的代幣。「一日跑路」在 BNB Chain 最常見，估計獲利約 2.4 億美元。另有狙擊機器人。這直接支持你第 (1) 項「內部人拿走大部分錢」。
- Daian 等，*Flash Boys 2.0*（arXiv 1904.05234，已開啟）：機器人用優先 gas 拍賣搶先交易，定義 MEV。散戶在鏈上交易處於資訊與速度劣勢。摘要無量化數字。
- Loesch 等，*Impermanent Loss in Uniswap v3*（arXiv 2111.09192，已開啟）：17 個池（約佔 43% TVL）。總手續費 1.993 億美元，無常損失 2.601 億美元。LP 整體比單純持有少約 6,080 萬美元。
- Heimbach, Schertenleib & Wattenhofer, *Risks and Returns of Uniswap V3 Liquidity Providers*（arXiv 2205.08904，已開啟）：簡單策略只在幾乎不波動的池獲利，且報酬有限。要有顯著報酬需承擔更多風險並主動管理。結論是「專業玩家的遊戲」。
- 加密貨幣散戶日內交易盈虧的同儕審查證據：我**沒有找到已驗證的加密貨幣專門研究**。搜尋到的是台灣與巴西股票、期貨的研究，且是二手轉述。**未驗證**，不在此引用數字。

## 5. 個人投資者的實務

- Man Group 的 Rzym、Fraikin、Abou Zeid（2024-12，網頁已開啟，非同儕審查）：加密貨幣的波動與缺乏基本面錨點，適合趨勢跟隨。幣間相關性約 0.6，分散效果有限。約 10-15 個幣是分散與成本的平衡點。用波動率調整部位可穩定風險。
- Moreira & Muir, *Volatility-Managed Portfolios*（NBER w22208；J. of Finance 72(4), 2017，已開啟）：波動管理在股票因子上提高夏普。但後續研究（Cederburg 等、Barroso & Detzel，僅搜尋摘要）指出樣本外與扣成本後會失效。這是股票證據，不是加密貨幣證據。
- AQR：有網站文章聲稱 AQR 自 2017 年操作加密趨勢策略。來源是泰文新聞，沒有論文。**未驗證**。我沒找到 AQR 自己的加密貨幣趨勢研究。
- 小資金能做的：用現貨或低槓桿，趨勢做 BTC/ETH，以降低回撤為主要目標。不要期待超額報酬。

## 6. 總表

| 想法 | 證據強度 | 對你結果的意義 |
|---|---|---|
| 買新幣 / 狙擊 | 弱（對散戶為負） | 你的負期望值有文獻支持。放棄 |
| 資金費率套利 | 混合。歷史強，近年報酬被壓縮 | 3.2% ≈ 穩定幣收益。不值得承擔交易所與強平風險 |
| 趨勢跟隨 BTC/ETH | 混合偏正。回撤改善較可靠，夏普優勢不穩 | 你的「回撤減半、夏普差不顯著」與文獻一致 |
| 橫斷面動能 / 多幣輪動 | 混合。成本與強平後變弱 | 小資金成本高。不建議優先做 |
| ML 預測報酬 | 弱 | 扣成本後多半消失。你的 AUC 0.65-0.68 不足以交易 |
| 提供 LP | 弱（整體虧損） | 對小資金不利 |
| 搶 MEV | 強但屬專業玩家 | 不適合散戶 |

## 建議

1. 把趨勢策略當「風險管理工具」，不是賺超額報酬的工具。目標是持有 BTC 但回撤減半。
2. 用 Deflated Sharpe 或 PBO 重新評估你試過的所有參數組合。把嘗試次數算進去。
3. 對趨勢策略做壓力測試：延遲一天、成本加倍、換不同均線。ETH 對這些最敏感，所以倉位應小於 BTC。
4. 加入波動率目標部位，並比較「有 / 無」的樣本外結果。只在扣成本後仍有改善時才採用。
5. 資金費率套利只作監控。若費率重新升到高水位（例如年化 15% 以上），再重新評估。同時計入保證金與強平風險。
6. 若結論仍是「沒有可靠 edge」，就接受這個結論，把錢放在簡單持有加風控上。這是誠實的答案。

## 來源（皆為我實際開啟或由搜尋取得）

已開啟：
- https://www.bis.org/publ/work1087.htm （Crypto carry）
- https://arxiv.org/abs/2310.11771 （Perpetual Futures Pricing）
- https://arxiv.org/abs/2212.06888 （Fundamentals of Perpetual Futures）
- https://www.nber.org/papers/w24877 （Risks and Returns of Cryptocurrency）
- https://www.nber.org/papers/w25882 （Common Risk Factors in Cryptocurrency）
- https://ideas.repec.org/p/chf/rpseri/rp2580.html （Catching Crypto Trends）
- https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178 （CTREND）
- https://arxiv.org/abs/2009.12155 （A Decade of Evidence of Trend Following）
- https://www.usenix.org/conference/usenixsecurity23/presentation/cernera
- https://arxiv.org/abs/1904.05234 （Flash Boys 2.0）
- https://arxiv.org/abs/2111.09192 （Impermanent Loss in Uniswap v3）
- https://arxiv.org/abs/2205.08904 （Risks and Returns of Uniswap V3 LPs）
- https://nber.org/papers/w20592 （Harvey, Liu, Zhu）
- https://www.risk.net/journal-of-computational-finance/2471206/the-probability-of-backtest-overfitting
- https://publikationen.bibliothek.kit.edu/1000150665 （Jaquart 2021）
- https://www.nber.org/papers/w22208 （Volatility Managed Portfolios）
- https://www.man.com/insights/in-crypto-we-trend 、 https://theideafarm.com/alternative-investment/real-assets/crypto/in-crypto-we-trend/

僅搜尋摘要（未讀全文）：
- Han, Kang & Ryu：https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf
- Bailey & López de Prado DSR：https://papers.ssrn.com/abstract=2460551
- Hudson & Urquhart：https://link.springer.com/article/10.1007/s10479-019-03357-1
- Jaquart, Köpke & Weinhardt (2022)、Cederburg 等、Barroso & Detzel：無直接 URL

## 未驗證項目清單

- Han/Kang/Ryu 的樣本期、成本數字、子期結果（全文 403）。
- Liu & Tsyvinski RFS 2021 的刊登細節；樣本期。
- Fieberg JFQA 的樣本期、成本後績效數字。
- Zarattini 等的 SSRN 版本（SSRN 403）。
- Hudson & Urquhart、Jaquart 2022、Cederburg、Barroso & Detzel（僅搜尋摘要）。
- Ackerer 等刊登於 Mathematical Finance 36(3) 的細節（僅搜尋摘要）。
- He 等 *Fundamentals of Perpetual Futures* 的正式刊登期刊。
- 加密貨幣動能「發表後衰退」的直接論文。
- 2023 年後 carry 衰退的同儕審查證據。
- AQR 的加密貨幣趨勢研究。
- 加密貨幣散戶日內交易盈虧的同儕審查研究。
