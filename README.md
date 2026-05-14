# 台股盤後報告自動化

每天台北時間 18:00 產生一份台股盤後 Markdown 報告，官方資料優先，缺資料時明確標示「尚未公布」或「資料待確認」。

## 使用方式

```powershell
python .\run_daily.py
python .\run_daily.py --date 2026-05-08
```

若本機 `python` 不在 PATH，可用 Codex workspace runtime：

```powershell
C:\Users\Lin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\run_daily.py
```

報告會輸出到：

```text
reports/YYYY-MM-DD.md
```

## 追蹤清單

建立 `watchlist.txt`，每行一檔股票代號，可使用 `#` 註解：

```text
2330
2454
# 2317
```

## 資料來源

- TWSE：上市盤後行情、三大法人、外資/投信個股買賣超。
- TPEx：上櫃盤後行情與籌碼資料，使用官方公開端點，失敗時會標示待確認。
- 公開資訊觀測站：營收、重大訊息與法說會資料入口保留於來源區；每日管線目前以可公開抓取的結構化資料為主。
- 國際市場：使用 Yahoo Finance chart API 作為補充行情來源，並在報告註明日期。
- 新聞：使用可信財經媒體 RSS 標題摘要，並以追蹤股代號/名稱優先篩選；預設會再抓新聞連結頁正文，抓不到時退回 RSS 摘要或標題。

## AI 新聞摘要設定

預設不需要付費模型；若沒有設定 API key，報告仍會正常產生，並保留新聞連結與正文抓取狀態。

```powershell
$env:AI_SUMMARY_PROVIDER="gemini"
$env:GEMINI_API_KEY="你的 Google AI Studio API key"
$env:AI_MODEL="gemini-2.5-flash-lite"
```

可用環境變數：

- `AI_SUMMARY_PROVIDER`：`gemini`、`ollama`、`openrouter`、`none`。未設定但有 `GEMINI_API_KEY` 時會自動使用 Gemini。
- `AI_MODEL`：模型名稱。Gemini 預設 `gemini-2.5-flash-lite`，Ollama 預設 `qwen3:4b`，OpenRouter 預設 `openrouter/free`。
- `NEWS_FETCH_BODY`：是否抓新聞內文，預設 `1`；設為 `0` 可關閉。
- `NEWS_RSS_LIMIT`：最多保留幾則 RSS 新聞，預設 `60`。
- `NEWS_MAX_ARTICLES`：最多抓幾篇新聞內文，預設 `30`。
- `NEWS_MAX_CHARS_PER_ARTICLE`：每篇保留的正文最大字數，預設 `1500`。
- `AI_MAX_NEWS_ITEMS`：最多送幾篇新聞給 AI 摘要，預設 `30`，會優先送追蹤個股新聞，再送大盤/國際股市新聞。
- `AI_MAX_CHARS_PER_ARTICLE`：每篇送給 AI 的最大字數，預設 `1500`。
- `AI_REQUEST_TIMEOUT`：AI API 讀取逾時秒數，預設 `360`。

## 測試

```powershell
python -m unittest discover -s tests
```
