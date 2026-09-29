# NInfer on a single Tesla V100 (sm_70): sm70 decode kernels + context-cache tuning, with a measured 53-request agent load run

**Chinese is the primary language of this repository: see [README.md](README.md).** This English file
carries the same numbers and the same corrections.

A working recipe for running a 27B dense model on **one** Tesla V100-SXM2-32GB through
[NInfer](https://github.com/geoffwatts/ninfer-v100), plus the raw logs behind the numbers.

Companion repository: [`ninfer-v100-splitd-kernel`](https://github.com/taskeee/ninfer-v100-splitd-kernel)
covers the **prefill** side (1CatAI Split-D D256). This repository covers the **decode** side, the
scheduler/context-cache settings, and the end-to-end behaviour under a real agent workload.

---

## A note about this repository

**This was published by an AI on behalf of the machine's owner.** He does not read English and does
not write code. He asked for the write-up to be posted because other people with the same card are
stuck, and he cannot answer technical questions about it — **if you have a question, please put it to
your own AI/assistant**; it can read these files, the raw logs under `logs/`, and the two upstream
repositories, which is more than he can do. Be kind: everything here that works, he paid for in
failed runs and a lot of waiting.

---

## Contents

| Item | Where |
|---|---|
| The measured 53-request agent load run | this file, [Results](#results-a-real-agent-workload) |
| Every claim mapped to its source line | [`claims.md`](claims.md) — **including which numbers are NOT traceable** |
| Raw engine logs (unmodified copies) | [`logs/`](logs/) |
| The A/B arms behind the kernel numbers | [`evidence/v2ab/`](evidence/v2ab/) (10 JSON files) |
| Console text of two failed starts | [`evidence/failed-startup-console.txt`](evidence/failed-startup-console.txt) — **console, not log** |
| Method and result of the pinned-memory probe | [`evidence/pinned-probe-notes.txt`](evidence/pinned-probe-notes.txt) — **raw probe output not published** |
| **A runnable start script + `.wslconfig` example** | [`launcher/`](launcher/) — no need to transcribe the flags; deliberately **no** Windows wrapper (that part is not portable — see that directory) |

**One honest sentence about evidence strength**: the raw measurements here (per-row table, the seven
integrity counts, the compaction details, the four A/B values, environment and startup) all reproduce
line by line from `logs/`. **Some claims do not** — the single-kernel-call timing, the two failed-start
FATAL lines, the pinned-memory probe, and the whole "what did NOT work" section come from unpublished
ledgers or console output. Each is marked `[not published with the evidence]` inline, and `claims.md`
lists them all.

---

## Test machine

| | |
|---|---|
| GPU | **Tesla V100-SXM2-32GB** (sm_70), 31,522 / 32,768 MiB **at capture** (96.2%), 33 °C |
| Second GPU | RTX 3080 Ti, display only, ~800 MiB at capture |
| Host | **63.15 GiB (67.8 GB)** RAM; WSL2 distro `Ubuntu-24.04`; `.wslconfig`: `memory=32GB`, `swap=8GB`, `networkingMode=nat` |
| Engine | NInfer `build-v100/apps/ninfer-serve`, 299,287,880 bytes, md5 `6b104a4464cdab6687351c00770d7ba8` (2026-09-28 22:13:04 +0800) |
| Model | `qwen3_8_27b_nvfp4.ninfer`, served as `qwen3.8-27b-uncen` |
| Client | DeepSeek Harness (DSH) web UI, 47 tool schemas, **single stream** |

Engine command line:

```
ninfer-serve qwen3_8_27b_nvfp4.ninfer
  --host 127.0.0.1 --port 8110 --model-id qwen3.8-27b-uncen
  --max-context 245000 --kv-capacity 245000 --prefill-chunk 2048
  --max-concurrency 1 --kv-dtype int8
  --device-state-slots 1 --host-state-slots 12 --host-kv-mib 14336
  --pending-timeout-ms 900000
  --max-private-continuations 4 --max-shared-prefixes 8 --max-long-anchors-per-continuation 8
  --spec mtp --draft-tokens 3 --lm-head-draft
  --vision --device 1
```

Environment: `NINFER_SM70_ATTN_V2=1`. Startup record (`logs/startup-raw.txt`):

```
weights ready | 20.0 GiB | 1m 3.6s | 322.3 MiB/s
pinning host state | 1.72 GiB   ->  host state pinned | 1.72 GiB | 1.5s
pinning host KV    | 14.0 GiB   ->  host KV pinned    | 14.0 GiB | 12.0s
engine ready | qwen3.8-27b/nvfp4 | total 1m 26.3s | weights 20.0 GiB
capacity | KV 245,056 tokens, int8, explicit | pages 3,829/3,829 | runtime 10.5 GiB | free 188.3 MiB
context cache | 1 active + 1 cached device states | host 12 states, 14.0 GiB KV | private 4 | shared 8 | anchors 8
```

---

## What was changed relative to a stock NInfer V100 build

Three of these are **ports of already-public sm70 kernels**; no kernel code here is original to this
machine. The fourth is configuration.

1. **Decode attention kernel** — `small_t_i8_volta_v2.cuh` from
   [huangserva/ninfer-v100-tpx](https://github.com/huangserva/ninfer-v100-tpx) (Apache-2.0), armed by
   `NINFER_SM70_ATTN_V2=1`. 8 warps / Bc=64: each warp computes the QK^T for its own 8 keys instead of
   4 warps recomputing the same 16-key QK^T+softmax, with row maxima exchanged through shared memory —
   3 synchronisations per 64 keys instead of 8.
2. **Six sm70 commits** from [Flo5k5/ninfer-v100-sm70](https://github.com/Flo5k5/ninfer-v100-sm70)
   (same base fork): int8 split-K QK^T, fp16 magic-bias dequantisation, MTP W8 GEMV, a fused GDN
   norm+gating kernel, and a 3-line T=4 WAR race fix.
3. **Prefill** — in the companion repository, not repeated here.
4. **Scheduler / context-cache settings** — next section.

### Why these settings

| Setting | Stock | Used | Reason |
|---|---:|---:|---|
| `--host-state-slots` | 8 | **12** | From the **engine source** (`src/targets/qwen3_6/impl/runtime/program_impl.h`): `logical_state_capacity = (max_concurrency + device_state_slots) + host_state_slots`, while the address space is `max_private_continuations + max_shared_prefixes + 1`. At the stock counts (4/8) that is 13, but only (1+1)+8 = 10 state images exist, so 3 checkpoints cannot be materialised. 2 + 12 = 14 >= 13. **Both counts and the source line are source-level reasoning, not log evidence**; only the ~147 MiB per **pinned** slot is derivable from the log (`pinning host state \| 1.72 GiB` / 12). |
| `--host-kv-mib` | 8192 | **14336** | Byte pool for reusable prefixes, pinned as ONE `cudaMallocHost`. Cost ~45 KiB/token, so 8192 MiB is ~187k tokens (less than one 245k window). **The ceiling is not RAM**: a probe on this box measured a maximum single `cudaMallocHost` of 15 GiB (16 GiB -> `cudaErrorMemoryAllocation`) while cumulative 2 GiB blocks reached 28 GiB; the cap was identical at `memory=32GB` and `memory=40GB`. 20 GiB was tried and the engine refused to start. |
| `--pending-timeout-ms` | 30000 | **900000** | Absolute preparation-plus-admission deadline. At 30 s any second request (a subagent, an auxiliary call) is **killed** with `HTTP 503 request_queue_timeout` instead of waiting. Waiting costs latency; dying costs the turn. |
| the three count flags | 2 / 4 / 2 | **4 / 8 / 8** | Descriptor counts, no memory cost (`address_capacity = private + shared + 1`). |

`--max-context` was **not** raised: the measured ceiling is
`11,330,617,856 B available / 45,794 B per token ~= 247,428 tokens`, so `245000` already has only
~2,400 tokens of slack. 262144 was tried and the engine refused to start.
⚠️ Both failed-start lines come from the launcher console; **the engine log for those attempts was
overwritten** by the later successful start. See `evidence/failed-startup-console.txt`.

---

## Results: a real agent workload

One continuous DSH session, 53 engine requests, a 27B agent growing its own context and driving the
client's automatic compaction loop. **Not a synthetic benchmark.** Raw lines:
`logs/done-lines-raw.txt`.

| req | prompt | cache % | reuse path | TTFT | prefill tok/s | **decode tok/s** | **MTP accept** |
|---:|---:|---:|---|---:|---:|---:|---:|
| 3 | 40,119 | 0.0 | root | 43.1 s | 1,000 | 55.5 | 49.0% |
| 7 | 49,540 | 99.7 | private endpoint | 0.71 s | 203.0 | 59.2 | 56.2% |
| 9 | 48,880 | 89.2 | turn closure | 7.3 s | 728.6 | 51.6 | 43.0% |
| 14 | 65,536 | 100.0 | private endpoint | 1.9 s | 14.2 | 56.0 | 50.5% |
| 24 | 88,096 | 96.9 | private endpoint | 4.7 s | 602.2 | 47.2 | 42.8% |
| 32 | 98,612 | 99.9 | private endpoint | 4.5 s | 11.9 | **89.4** | **83.1%** |
| 33 | 88,528 | 0.0 | root (probe) | 1 m 46.8 s | 829.8 | 72.4 | 94.4% |
| 37 | 134,156 | 0.0 | root | 3 m 57.6 s | 565.0 | 53.2 | 59.4% |
| 38 | 167,428 | 80.4 | private endpoint | 1 m 11.2 s | 460.9 | 55.8 | 68.6% |
| 39 | 201,700 | 83.2 | private endpoint | 1 m 23.7 s | 404.8 | 49.2 | 63.0% |
| 40 | 81,919 | 59.7 | turn closure | 51.0 s | 648.7 | **67.4** | 69.1% |
| 41 | 136,497 | 0.0 | root | 3 m 20.2 s | 688.3 | 44.9 | 45.7% |
| 43 | 175,017 | 0.0 | root | 4 m 44.2 s | 616.1 | 46.4 | 54.7% |
| 44 | 206,364 | 67.2 | turn closure | 2 m 40.8 s | 422.5 | **42.3** | 51.3% |
| 45 | 88,228 | 0.0 | root | 1 m 51.2 s | 799.6 | 66.3 | 68.4% |
| 47 | 183,938 | 73.8 | turn closure | 1 m 49.2 s | 444.0 | 46.6 | 57.0% |
| 48 | 136,960 | 0.0 | root | 3 m 20.1 s | 689.8 | 58.5 | 67.3% |
| 49 | 113,562 | 0.0 | root | 2 m 30.9 s | 756.0 | 58.4 | 66.2% |
| 50 | 114,286 | 99.4 | turn closure | **1.8 s** | 429.8 | 57.9 | 63.2% |
| 51 | 146,219 | 78.2 | turn closure | 1 m 4.1 s | 501.5 | 52.5 | 62.6% |
| 52 | 172,414 | 99.8 | private endpoint | 1.6 s | 280.4 | 50.6 | 62.1% |
| 53 | 175,632 | 100.0 | private endpoint | 7.7 s | 7.0 | 52.1 | 65.2% |

Rows 40, 45 and 48 are the **compaction summary calls**. The identification rests on
`max output 8,192` (the client's default summarisation cap — it occurs exactly 3 times in this snapshot; the full
`max output` histogram is 32,768 x47, 8,192 x3, and 24/64/96 x1 each), plus: each immediately follows an over-threshold request (by
0.12 s / 3.87 s / 0.09 s), the message count collapses (104->73->38, 49->32->24, 29->25->12), and each
ends on a stop token after emitting 2,773–4,491 tokens.
⚠️ **This is an inference, not a logged fact** — the engine log has no compaction/summarize field and
does not record prompt content. If your client uses `max output 8,192` for something else, the
identification does not hold.

**About the "reuse path" column**: on a hit the log prints a path label (`private endpoint` /
`turn closure` / `shared prefix`). **On a miss it prints no label at all, only `cache 0 (0.0%)`.**
`root` in the table is **a label added by me** (`root` is the engine documentation's name for that
path); the "(probe)" note comes from the workload's own ledger, **not from the engine log**.

**Decode must be read together with acceptance.** In the table above the two slowest rows (42.3 / 44.9)
sit at 51.3% / 45.7% acceptance. But do **not** treat a few high values as "the fastest": the real
decode highs in this session are req#32 = 89.4 (83.1%), req#8 = 75.1, req#33 = 72.4, req#29 = 71.1 and
req#23 = 70.1 — and req#8/#29/#23 are **not** in the table (it lists one representative row per band).

Summary, cache-hit rows only (>=99% reuse): TTFT **0.54 – 7.7 s**.
Cache-miss rows (`cache 0.0%`, 9 of 53 at real depth): TTFT **43 s – 4 m 44 s** — the whole prompt is
prefilled (`TTFT ~= prompt / prefill rate`).

### Integrity of the run

```
started = 53     done = 53
rejected = 0     failed = 0
HTTP 503 = 0     HTTP 400 = 0
OOM / CUDA errors = none
engine processes = 1 throughout
```

### Depth behaviour

⚠️ **This table was disproved by an independent review on 2026-09-29 (3 of its 4 rows were wrong) and
has been rewritten from the per-row values.** The earlier version generalised one five-row window
(53–58) to the whole "<=167k" band, and dropped responses that fall inside the other two bands
(#39/#53, #41/#50). **That was an aggregation error; the raw rows were never wrong.**
**For anything quantitative go back to the per-row table above** — the table below only answers "who
is in this band, and what are the real min/max".

| band (which reqs) | n | decode tok/s | prefill tok/s | MTP accept |
|---|---:|---|---|---|
| <=167k (prompt 40k–167,428, minus 3 summary calls) | 42 | **44.9 – 89.4** | 10.5 – 1000 | **42.8 – 94.4%** |
| 175k–206k (#39 #43 #44 #47 #53) | 5 | **42.3 – 52.1** | 7.0 – 616.1 | 51.3 – 65.2% |
| after compaction, 113k–138k (#41 #46 #49 #50) | 4 | **44.9 – 58.4** | 429.8 – 756.0 | 45.7 – 66.2% |
| summary calls (#40 #45 #48) | 3 | 58.5 – 67.4 | 648.7 – 799.6 | 67.3 – 69.1% |

**How to read it**: **the prefill column's extremes mean nothing** — turns that are shallow, or that
add only a few dozen tokens, divide by a tiny denominator and produce numbers like 1000 or 7.0 tok/s.
**TTFT is the readable quantity here**, and the spread inside each band comes mostly from acceptance,
not from depth.

**The only depth claim that survives**: inside the 175k–206k five rows, decode 42.3–52.1 and
acceptance 51.3–65.2% are both below the **median** of the <=167k band (56.1%) — though 15 of that
band's 42 rows also sit below 51.3%, so this is not a clean separation — and after compaction back to
113k–138k those 4 rows read 44.9–58.4 (3 of them 57.3–58.4). **The direction is consistent; the mechanism is not
established** — it is consistent with KV pressure (245k int8 KV pool, 32 GB device, 14 GiB host
offload), but no counter-evidence was collected.

---

## The compaction loop (3 cycles, all measured)

The client compacts at a nominal 80% of the declared 245k window. Three cycles fired; each appears in
the engine log as a summary request with `max output 8,192`.

| cycle | session prompt before | summary call | after | recovery |
|---|---|---|---|---|
| 1 | req#39 · 201,700 | req#40 · 81,919 -> 4,209 out · 1 m 53.6 s · 67.4 tok/s · 59.7% cache | req#41 · 136,497 · **cache 0%** · TTFT 3 m 20.2 s | req#42 · 98.5% |
| 2 | req#44 · 206,364 | req#45 · 88,228 -> 2,773 out · 2 m 33.1 s · 66.3 tok/s | req#46 · 138,406 · **cache 0%** · TTFT 3 m 24.0 s | — |
| 3 | req#47 · 183,938 | req#48 · 136,960 -> 4,491 out · 4 m 37.1 s · 58.5 tok/s | req#49 · 113,562 · **cache 0%** · TTFT 2 m 30.9 s | req#50 · **99.4%**, TTFT 1.8 s |

`cache 0%` immediately after each compaction is **by design**: NInfer's own documentation states that
*every checkpoint invalidates reuse from the first replaced history token*, and the summary is
inserted at the front of the conversation.

**The real per-cycle cost (measured, do not average it away):**

| cycle | generate summary | re-prefill after | total |
|---|---:|---:|---:|
| 1 | 1 m 53.6 s | 3 m 20.2 s | **5 m 13.8 s** |
| 2 | 2 m 33.1 s | 3 m 24.0 s | **5 m 57.1 s** |
| 3 | 4 m 37.1 s | 2 m 30.9 s | **7 m 8.0 s** |

⚠️ An earlier version said "roughly 5 minutes per cycle (~2 min to generate the summary)". That was
disproved: **cycle 3 totals 7 m 8 s, and its summary generation alone took 4 m 37 s, not ~2 minutes.**
**More memory does not fix this** — the prefix genuinely changed.

**One inconsistency about the "80% trigger"**: cycle 3 fired while the provider reported only
**183,938**, below the nominal 196,000. The client's pressure meter estimates dense ASCII text with a
character heuristic that does not match real token counts (measured ~1.35 chars/token for that shape
against a 4-chars/token assumption). **So "threshold 196,000" is nominal, not a hard edge.** This
explanation comes from the client's ledger, **not from anything this repository can prove**.

---

## Kernel A/B numbers (decode)

Same machine, same prompt (170,607 tokens), `--greedy`, K=3, int8 KV. Raw arms in `evidence/v2ab/`;
the `long-cold` result of each arm is the figure used.

| arm | file | decode tok/s | MTP accept |
|---|---|---:|---:|
| stock kernel, `--spec mtp` | `v2ab-v2off-200k.json` | 32.5653 | 0.5209 |
| ported v2 kernel, `--spec mtp` | `v2ab-flo-v2-200k.json` | **59.1960** | 0.7431 |
| stock kernel, `--spec none` | `v2ab-v2off-nospec-200k.json` | 15.2077 | — |
| ported v2 kernel, `--spec none` | `v2ab-flo-nospec-v2-200k.json` | **21.8427** | — |

The `--spec none` pair is the honest one: with speculative decoding on, the two arms diverge in
generated content (different floating-point accumulation order), so acceptance differs and part of the
apparent gain is not the kernel. Acceptance-free: **15.2077 -> 21.8427 = +43.6%**. Full precision:
`21.842699455932266 / 15.20774511610815 - 1 = 0.436287844...`.

⚠️ `[not published with the evidence]` The decode kernel call itself is reported as
**1.637 ms -> 0.689 ms median (2.38x, n=101 per arm)** at a >=100k-key window. That figure comes from a
separate trace analysis on this machine and **neither `logs/` nor `evidence/` contains that trace
data**. The ratio 1.637/0.689 = 2.3759 is arithmetically self-consistent, but self-consistency is not
evidence.

---

## Known limits and unverified items — read this before relying on any of it

1. **Byte-exactness of the ported kernels is NOT verified.** The decode kernel changes
   floating-point accumulation order, so greedy output at long depth *diverges* from the pre-port
   build. Token-level equivalence was never demonstrated.
2. **The engine died silently once.** After a 193k rewrite request: client `RemoteDisconnected`, log
   stops mid-prefill, **no error line**, 188 MiB free on the device. Reproduced once, never explained.
3. **The 245k wall is reachable and cannot be fixed engine-side.** `--max-context 245000` gates the
   *prepared* prompt (system + tool schemas + history). A single oversized tool result can jump past
   it in one step, and neither client compaction nor NInfer's overflow recovery can repair it when the
   newest indivisible unit is itself too large. Measured ceiling ~247,428 tokens.
4. **~15.72 GiB of pinned host RAM is the price of prefix reuse** (14.0 GiB host KV + 1.72 GiB host
   state; both from the `pinning host` lines in `startup-raw.txt`). An earlier version said 9.7 GiB —
   a leftover from the previous 8 GiB configuration; corrected. `--no-prefix-reuse` reduces it to zero
   at the cost of a full prefill every turn.
5. **Numbers are for one machine.** SXM2 (~900 GB/s) not PCIe (~780 GB/s), 63.15 GiB host, single
   stream, one artifact.
6. **The 175–206k slowdown has no established cause.**
7. `--max-concurrency 1` is deliberate: the KV pool is sized for one sequence. NInfer's docs accept
   1..8 — it is a capacity question, not a flag restriction.

## What did NOT work (so you do not have to try it)

⚠️ **`[not published with the evidence]` — nothing in this section is traceable to `logs/`.** It comes
from this machine's unpublished engine ledger and from bash semantics.

- `--kv-dtype fp8` — prefill -88%, decode -88%, TTFT 12.7 s -> 1 m 50 s. Volta has no native fp8 path.
- `--kv-dtype nvfp4` / `k8v4` — **rejected outright on Volta**: `FATAL ... NVFP4 KV-cache storage is
  unavailable on Volta` within 32 ms. There is no way to double KV capacity on this card.
- `--prefill-chunk 8192` — prefill -41%. `2048` is the measured optimum.
- `--media-cache-mib` / `--media-live-mib` — budgets, not preallocations; changing them does not change
  VRAM or speed.
- Raising `--max-context` — see limit 3.
- **A subagent / second concurrent stream at depth** — the second request queues behind a 40–170 s
  prefill and, at the 30 s default `--pending-timeout-ms`, is killed with HTTP 503. The fix is the
  timeout, not more VRAM.
- `exec VAR=1 cmd` in a launcher — bash parses the assignment as the program name. Put it **before**
  `exec`.
- **Two launcher files where only one is live** — this cost two separate outages here (a fix landed on
  the stale copy twice; the second time it silently dropped `--vision`, so every image turn failed with
  `400 vision_disabled`). Keep exactly one canonical launcher.

## Attribution and licences

No kernel in this recipe is original work by this machine's owner.

| Component | Source | Licence |
|---|---|---|
| NInfer engine | [geoffwatts/ninfer-v100](https://github.com/geoffwatts/ninfer-v100) | see that repository |
| Split-D D256 prefill kernel | [fishlikeX/sm70-attn](https://github.com/fishlikeX/sm70-attn) | MIT (companion repository) |
| `small_t_i8_volta_v2.cuh` decode kernel | [huangserva/ninfer-v100-tpx](https://github.com/huangserva/ninfer-v100-tpx) | Apache-2.0 |
| Six sm70 commits | [Flo5k5/ninfer-v100-sm70](https://github.com/Flo5k5/ninfer-v100-sm70) | **verify before redistributing** |

**This repository contains no kernel source.** Obtain the code from the upstream repositories above and
check each licence yourself.

## How the numbers were checked, and what was corrected

**Not every figure here is traceable to `logs/`.** An earlier version claimed it was; an independent
review disproved that, and it has been fixed. Traceable line by line: **the per-row table, the seven
integrity counts, the compaction details, the four A/B values, environment and startup.** Not
traceable (each marked `[not published with the evidence]` inline): the single-kernel-call timing, the
two failed-start FATAL lines, the pinned-memory probe, and the whole "what did NOT work" section.

```sh
L=ninfer-serve.log
grep -ac 'req#[0-9]* started'          "$L"   # 53
grep -ac ' done | '                    "$L"   # 53
grep -ac 'rejected during'             "$L"   # 0
grep -ac 'failed during'               "$L"   # 0
grep -ac 'queue timeout'               "$L"   # 0
grep -ac 'context length exceeded'     "$L"   # 0
grep -aE 'max output 8,192'            "$L"   # 3 summary calls
```

### Corrections (2026-09-29, after one independent review)

After publication, a process that had **not** produced any of this content recomputed 126 assertions
from the raw files: **103 passed, 19 did not, 4 could not be checked. It was right — these are the
corrections.** They are listed so you can see the document was reviewed and where it was wrong:

| Originally said | Actually | Now |
|---|---|---|
| depth table "<=167k = decode 53–58" | per-row 44.9–89.4; **24 of 42 rows** outside [53, 58] | rewritten from per-row values, with the cause stated |
| "175k–206k = 42–47 / 422–444" | that band has 5 rows (#39, #53 were dropped); prefill 7.0–616.1 | rewritten, req numbers listed |
| "after compaction = 57–58" | true only for 2 rows; #41 (44.9) and #50 were dropped | rewritten (44.9–58.4, n=4) |
| "about 5 minutes per compaction" | 5 m 13.8 s / 5 m 57.1 s / **7 m 8.0 s** | per-cycle measured table |
| "~9.7 GiB pinned" | 1.72 + 14.0 = **15.72 GiB** (9.7 was stale) | corrected |
| "every figure is traceable to logs/" | four classes are not | listed explicitly, plus the two extra `evidence/` files |
| "the three second-hand items are labelled in the README" | they were **not** labelled | labelled inline now |
| "the fastest (89.4 / 67.4 / 66.3)" | real highs are 89.4 / 75.1 / 72.4 / 71.1 / 70.1 | corrected |
| "peak 31,522 MiB" | a single sample | "at capture" |
| "host 63.1 GB" | 63.15 **GiB** (67.8 GB) | unit corrected |
| a `claims.md` note claiming "rounding gives 0.4359" | it is 0.436292 | removed (+43.6% itself was correct) |

**Not disproved**: the per-row table (22 rows x 7 columns), the seven integrity counts, the nine
compaction prompt values and the three summary details, the four A/B values and +43.6%, the 13
environment/startup items, and byte-identical parity between the 22 published files and the local
copies — **all matched, zero fabrication.**

⚠️ The lesson: **raw rows are trustworthy; aggregation is not.** For any band claim, go back to the
per-row table and recompute it yourself.