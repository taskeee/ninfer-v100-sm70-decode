# `data/` — the measured session, machine-readable

**English** — `session-53-requests.csv` is the same 53 requests that the top-level README summarises, parsed
straight out of [`../logs/done-lines-raw.txt`](../logs/done-lines-raw.txt) (per-request `done` lines) joined with
[`../logs/req-events-raw.txt`](../logs/req-events-raw.txt) (per-request `started` lines: message count, `max output`,
thinking level). **No value is hand-transcribed.** Generated 2026-09-29.

## Columns

| Column | Meaning |
|---|---|
| `req` | engine request number, 1–53 |
| `done_at`, `finish` | timestamp and finish reason of the `done` line (`output limit` / `stop token` / `tool calls N`) |
| `messages` | conversation length in messages at request start (from the `started` line) |
| `max_output` | the request's output cap as the client sent it (32,768 normal; **8,192 on the 3 summary calls**) |
| `thinking` | thinking level the client sent (`xhigh` / `medium`) |
| `prompt_tokens`, `output_tokens` | as reported by the engine |
| `cache_tokens`, `cache_pct` | how much of the prompt was reused from cache |
| `reuse_path_as_printed` | the label the engine printed on a cache hit (`private endpoint` / `turn closure` / `shared prefix`); **empty on a miss — the engine prints no label then** |
| `reuse_path_annotated` | the same, with the miss case annotated as `root`. **The annotation is ours, not the engine's** |
| `ttft_s`, `total_s`, `queue_ms` | seconds to first token, total wall clock, queue wait (`queue_ms` is empty on some rows — the engine omits the field) |
| `prefill_tok_s` | prompt-processing rate. ⚠️ **Its extremes carry no information**: a near-100% cache hit leaves only a few dozen tokens to prefill, so the denominator is tiny (values like 1000 or 7.0 tok/s) |
| `decode_tok_s` | generation rate. ⚠️ **Only meaningful together with `mtp_accept_pct`** — they are not independent |
| `mtp_accepted` / `mtp_proposed` / `mtp_accept_pct` | speculative-decoding (MTP) acceptance. Empty where the arm ran without speculation |
| `note` | our annotation only: `client-side compaction summary call (INFERRED…)` for req 40/45/48, `cache miss: full re-prefill` otherwise |

## Two things this file cannot prove

1. **Which rows are compaction summaries is an inference.** The engine log has no compaction field. The evidence is
   `max_output = 8,192` appearing exactly 3 times, three over-threshold requests immediately before them, message-count
   collapses, and long `stop token` outputs. See the README's §2.1.
2. **`root` is our annotation for a cache miss.** The engine prints a path label only on a hit.

## Cross-checks (recomputed from this file)

- 53 rows; `started 53 / done 53`; zero 400 / 503 / OOM / FATAL in the engine log.
- Deep cache misses (`cache_pct == 0` and `prompt_tokens >= 40000`): **9 rows**, TTFT 43.1 s – 284.2 s.
- Cache hits (`cache_pct >= 99`): **21 rows**, TTFT 0.54 – 7.70 s.
- Band `40,000 ≤ prompt ≤ 167,428` excluding the 3 summaries: **42 rows**, decode 44.9 – 89.4 tok/s.
- Band `175,000–206,364` (#39 #43 #44 #47 #53): decode 42.3 – 52.1 tok/s.
- Summary calls: `max_output` 8,192 ×3, outputs 4,209 / 2,773 / 4,491.

---

**中文** —— `session-53-requests.csv` = README 里那张总表背后的**全部 53 条请求**，由
`logs/done-lines-raw.txt`（每请求一行 `done`）与 `logs/req-events-raw.txt`（每请求一行 `started`：消息数、
`max output`、思考档）**直接解析而来，没有一个值是人手抄的**。生成时间 2026-09-29。

列含义见上表（英文）。两条必须知道的边界：**① 「哪三行是压缩摘要」是推断**（引擎日志没有压缩字段，
依据是 `max output 8,192` 全文只出现 3 次 + 紧跟越阈请求 + 消息数塌缩）；**② 未命中时引擎不打印路径标签**，
表里的 `root` 是我们的加注。预填列（`prefill_tok_s`）的极值没有解释力，解码列（`decode_tok_s`）
必须与接受率（`mtp_accept_pct`）成对读。
