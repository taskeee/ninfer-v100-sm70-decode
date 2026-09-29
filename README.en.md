# NInfer on a single Tesla V100 (sm_70): sm70 decode kernels + context-cache tuning, with a measured 53-request agent load run

A working recipe for running a 27B dense model on **one** Tesla V100-SXM2-32GB through
[NInfer](https://github.com/geoffwatts/ninfer-v100), plus the raw logs behind every number here.

Companion repository: [`ninfer-v100-splitd-kernel`](https://github.com/taskeee/ninfer-v100-splitd-kernel)
covers the **prefill** side (1CatAI Split-D D256). This repository covers the **decode** side, the
scheduler/context-cache settings, and the end-to-end behaviour under a real agent workload.

---

## A note about this repository

**This was published by an AI on behalf of the machine's owner.** He does not read English and does
not write code. He asked for the write-up to be posted because other people with the same card are
stuck, and he cannot answer technical questions about it — **if you have a question, please put it
to your own AI/assistant**; it can read these files, the raw logs under `logs/`, and the two upstream
repositories, which is more than he can do. Be kind: everything here that works, he paid for in
failed runs and a lot of waiting.

---

## What is in here

| Item | Where |
|---|---|
| The measured 53-request agent load run (tables) | this file, [Results](#results-a-real-agent-workload) |
| Every number's raw source line | [`claims.md`](claims.md) |
| Raw engine logs (immutable copies) | [`logs/`](logs/) |
| The A/B arms behind the kernel numbers | [`evidence/v2ab/`](evidence/v2ab/) |

---

## Test machine

| | |
|---|---|
| GPU | **Tesla V100-SXM2-32GB** (sm_70), 31,522 / 32,768 MiB peak (96.2%), 33 °C at capture |
| Second GPU | RTX 3080 Ti, display only, ~800 MiB used throughout |
| Host | 63.1 GB RAM, WSL2 Ubuntu-24.04, `.wslconfig`: `memory=32GB`, `swap=8GB`, `networkingMode=nat` |
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

Environment: `NINFER_SM70_ATTN_V2=1`.
Startup record (verbatim, `logs/startup-raw.txt`):

```
weights ready   | 20.0 GiB | 1m 3.6s | 322.3 MiB/s
pinning host state | 1.72 GiB
host state pinned  | 1.72 GiB | 1.5s
pinning host KV | 14.0 GiB
host KV pinned  | 14.0 GiB | 12.0s
engine ready | qwen3.8-27b/nvfp4 | total 1m 26.3s | weights 20.0 GiB
capacity | KV 245,056 tokens, int8, explicit | pages 3,829/3,829 | runtime 10.5 GiB | free 188.3 MiB
context cache | 1 active + 1 cached device states | host 12 states, 14.0 GiB KV | private 4 | shared 8 | anchors 8
```

---

## What was changed relative to a stock NInfer V100 build

Three of these are **ports of already-public sm70 kernels**; none of the kernel code is original to
this machine. The fourth is configuration.

1. **Decode attention kernel** — `small_t_i8_volta_v2.cuh` from
   [huangserva/ninfer-v100-tpx](https://github.com/huangserva/ninfer-v100-tpx) (Apache-2.0),
   compiled in and armed by `NINFER_SM70_ATTN_V2=1`. 8 warps / Bc=64: each warp computes the QK^T
   for its own 8 keys instead of 4 warps recomputing the same 16-key QK^T+softmax, with the row
   maxima exchanged through shared memory — 3 synchronisations per 64 keys instead of 8.
2. **Six sm70 commits** from [Flo5k5/ninfer-v100-sm70](https://github.com/Flo5k5/ninfer-v100-sm70)
   (same base fork): int8 split-K QK^T, fp16 magic-bias dequantisation, MTP W8 GEMV, a fused GDN
   norm+gating kernel, and a 3-line T=4 WAR race fix (the stock tree carries that hazard).
3. **Prefill** — covered in the companion repository, not repeated here.
4. **Scheduler / context-cache settings** — see the next section.

### Why these four settings

| Setting | Stock default | Used here | Reason (measured) |
|---|---:|---:|---|
| `--host-state-slots` | 8 | **12** | `logical_state_capacity = (max_concurrency + device_state_slots) + host_state_slots`. With 4 private + 8 shared + 1 addresses (13) and only 10 state images, addressable checkpoints cannot be materialised. 2 + 12 = 14 ≥ 13. Costs ~147 MiB per slot of pinned host RAM. |
| `--host-kv-mib` | 8192 | **14336** | Byte pool for reusable cross-request prefixes. Cost is ~45 KiB/token, so 8192 MiB ≈ 187k tokens (< one 245k window). **Ceiling is not RAM:** a CUDA probe on this box measured a maximum **single** `cudaMallocHost` of 15 GiB (16 GiB → `cudaErrorMemoryAllocation`), while **cumulative** 2 GiB blocks reached 28 GiB. The engine pins host KV in one call, so ~15 GiB is the hard limit and it does **not** scale with `.wslconfig` memory (identical at 32 GB and 40 GB). 20 GiB was tried: the engine refused to start with `cudaMallocHost failed: cudaErrorMemoryAllocation`. |
| `--pending-timeout-ms` | 30000 | **900000** | Absolute preparation-plus-admission deadline. At the 30 s default, any second request (a subagent, an auxiliary call) is **killed** with `HTTP 503 request_queue_timeout` instead of waiting. Waiting costs latency; dying costs the turn. |
| `--max-private-continuations` / `--max-shared-prefixes` / `--max-long-anchors-per-continuation` | 2 / 4 / 2 | **4 / 8 / 8** | These are descriptor counts, not memory (`address_capacity = private + shared + 1`); they do not shrink the per-checkpoint byte budget. |

`--max-context` was **not** raised. The measured ceiling is `11,330,617,856 B available ÷ 45,794 B
per token ≈ 247,428 tokens`, so `245000` already has only ~2,400 tokens of slack. 262144 was tried
and the engine refused: `requested Engine runtime reservation requires 12004767744 bytes, but only
11330617856 bytes are available`.

---

## Results: a real agent workload

One continuous DSH session, 53 engine requests, driving a 27B agent that grows its own context and
runs the client's automatic compaction loop. **Not a synthetic benchmark**: every row is a real
agent turn. Raw lines: `logs/done-lines-raw.txt`.

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

Rows 40, 45 and 48 are the **compaction summary calls** (identifiable by `max output 8,192`, the
client's default summarisation cap); they are included because they are engine work too.

**Read decode together with the acceptance rate.** The two are not independent: the slowest rows
(42.3, 44.9, 46.4) all sit at 45–55% acceptance, the fastest (89.4, 67.4, 66.3) at 68–83%. Quoting
a decode figure without its acceptance rate is meaningless on this stack.

Summary, cache-hit rows only (≥99% reuse): TTFT **0.54 – 7.7 s**.
Cache-miss rows (`cache 0.0%`, 9 of 53 at real depth): TTFT **43 s – 4 m 44 s**, because the whole
prompt is prefilled (`TTFT ≈ prompt ÷ prefill rate`).

### Integrity of the run

```
started  = 53      done = 53
rejected = 0       failed = 0
HTTP 503 = 0       HTTP 400 = 0
OOM / CUDA errors  = none
engine processes   = 1 throughout
```

### Depth behaviour

| depth band | decode | prefill | MTP accept |
|---|---|---|---|
| ≤ 167k | 53 – 58 tok/s | 616 – 799 tok/s | 59 – 69% |
| 175k – 206k | **42 – 47 tok/s** | **422 – 444 tok/s** | **51 – 57%** |
| after compaction, 113k – 138k | 57 – 58 tok/s | 685 – 756 tok/s | 63 – 67% |
| compaction summary calls (82k – 137k) | 58 – 67 tok/s | 649 – 800 tok/s | 67 – 69% |

All three metrics drop together in the 175–206k band and recover after compaction. The **mechanism
is not established** — it is consistent with KV pressure (245k int8 KV pool, 32 GB device, 14 GiB
host offload), but no counter evidence was collected. Treat the cause as unknown; treat the
observation as measured.

---

## The compaction loop (3 cycles, all measured)

The client compacts at 80% of the declared 245k window. Three cycles fired; each is visible in the
engine log as a summary request with `max output 8,192`.

| cycle | session prompt before | summary call | after | recovery |
|---|---|---|---|---|
| 1 | req#39 · 201,700 | req#40 · 81,919 → 4,209 out · 1 m 53.6 s · 67.4 tok/s · 59.7% cache | req#41 · 136,497 · **cache 0%** · TTFT 3 m 20.2 s | req#42 · 98.5% |
| 2 | req#44 · 206,364 | req#45 · 88,228 → 2,773 out · 2 m 33.1 s · 66.3 tok/s | req#46 · 138,406 · **cache 0%** · TTFT 3 m 24.0 s | — |
| 3 | req#47 · 183,938 | req#48 · 136,960 → 4,491 out · 4 m 37.1 s · 58.5 tok/s | req#49 · 113,562 · **cache 0%** · TTFT 2 m 30.9 s | req#50 · **99.4%**, TTFT 1.8 s |

The `cache 0%` immediately after each compaction is **by design**, not a bug: NInfer's own
documentation states that *every checkpoint invalidates reuse from the first replaced history
token*, and the summary is inserted at the front of the conversation, so almost nothing before it
can be reused. **Budget roughly 5 minutes per compaction cycle** (≈2 min to generate the summary,
≈3 min to re-prefill the compacted history). It is not avoidable by adding memory.

Observation, cause not established: in cycle 1 the summary call reused 59.7% of the session prefix;
in cycles 2 and 3 it reported 0%.

---

## Kernel A/B numbers (decode)

Measured on the same machine, same prompt (170,607 tokens), `--greedy`, K=3, int8 KV. Raw arms are
in `evidence/v2ab/`; the `long-cold` result of each arm is the figure used.

| arm | file | decode tok/s | MTP accept |
|---|---|---:|---:|
| stock kernel, `--spec mtp` | `v2ab-v2off-200k.json` | 32.5653 | 0.5209 |
| ported v2 kernel, `--spec mtp` | `v2ab-flo-v2-200k.json` | **59.1960** | 0.7431 |
| stock kernel, `--spec none` | `v2ab-v2off-nospec-200k.json` | 15.2077 | — |
| ported v2 kernel, `--spec none` | `v2ab-flo-nospec-v2-200k.json` | **21.8427** | — |

The `--spec none` pair is the honest one: with speculative decoding on, the two arms diverge in
generated content (different floating-point accumulation order), so the acceptance rates differ and
part of the apparent gain is not the kernel. Acceptance-free: **15.2077 → 21.8427 = +43.6%.**
The decode kernel call itself, at a ≥100k-key window, measured **1.637 ms → 0.689 ms median (2.38×,
n=101 per arm)**.

---

## Known limits and unverified items — read this before relying on any of it

1. **Byte-exactness of the ported kernels is NOT verified.** The decode kernel changes
   floating-point accumulation order, so greedy output at long depth *diverges* from the pre-port
   build. Token-for-token equivalence was never demonstrated. The upstream kernel test suite passes
   with both switches, but that is not the same claim.
2. **The engine died silently once.** After a 193k rewrite request: client `RemoteDisconnected`, log
   stops mid-prefill, **no error line**, device had 188 MiB free. Reproduced once, never explained.
   A silent death with no log line is the single worst failure mode in this setup.
3. **The 245k wall is reachable and cannot be fixed engine-side.** `--max-context 245000` gates the
   *prepared* prompt (system + tool schemas + history). A single oversized tool result can jump past
   it in one step, and neither client compaction nor NInfer's overflow recovery can repair it when
   the newest indivisible unit is itself too large. Measured ceiling: ~247,428 tokens.
4. **~9.7 GiB of pinned host RAM is the price of prefix reuse** (14.0 GiB host KV + 1.72 GiB host
   state). `--no-prefix-reuse` reduces it to zero at the cost of a full prefill every turn. The
   single-allocation limit is ~15 GiB and does not scale with WSL memory — see the table above.
5. **Numbers are for one machine.** SXM2 (≈900 GB/s) rather than PCIe (≈780 GB/s), 63 GB host,
   single stream, one model artifact. Do not expect the same figures elsewhere unchanged.
6. **The 175–206k slowdown has no established cause** (see above).
7. `--max-concurrency 1` is a deliberate choice: the KV pool is sized for one sequence. A second
   stream cannot be served at depth, and NInfer's own docs note `--max-concurrency` accepts 1..8 —
   it is a capacity question, not a flag restriction.

## What did NOT work (so you do not have to try it)

- `--kv-dtype fp8` — prefill −88%, decode −88%, TTFT 12.7 s → 1 m 50 s. Volta has no native fp8
  path; it falls back to per-element dequantisation.
- `--kv-dtype nvfp4` / `k8v4` — **rejected outright on Volta**: `FATAL ... NVFP4 KV-cache storage is
  unavailable on Volta` within 32 ms. There is no way to double KV capacity on this card.
- `--prefill-chunk 8192` — prefill −41%. 1024 is slightly worse at shallow depth, equal deep.
  `2048` is the measured optimum.
- `--media-cache-mib` / `--media-live-mib` — these are **budgets, not preallocations**; changing
  them does not change VRAM or speed.
- Raising `--max-context` — see limit 3; the card cannot back it.
- **A subagent / second concurrent stream while running at depth** — the second request queues
  behind a 40–170 s prefill and, at the 30 s default `--pending-timeout-ms`, is killed with HTTP
  503. The fix is the timeout, not more VRAM.
- `exec VAR=1 cmd` inside the launcher — bash parses the assignment as the program name. Put the
  assignment **before** `exec`.
- **Two launcher files where only one is live** — this cost two separate outages here (a fix landed
  on the stale copy twice; the second time it silently dropped `--vision`, so every image turn
  failed with `400 vision_disabled`). Keep exactly one canonical launcher.

## Attribution and licences

No kernel in this recipe is original work by this machine's owner.

| Component | Source | Licence |
|---|---|---|
| NInfer engine | [geoffwatts/ninfer-v100](https://github.com/geoffwatts/ninfer-v100) | see that repository |
| Split-D D256 prefill kernel | [fishlikeX/sm70-attn](https://github.com/fishlikeX/sm70-attn) | MIT (companion repository) |
| `small_t_i8_volta_v2.cuh` decode kernel | [huangserva/ninfer-v100-tpx](https://github.com/huangserva/ninfer-v100-tpx) | Apache-2.0 |
| Six sm70 commits | [Flo5k5/ninfer-v100-sm70](https://github.com/Flo5k5/ninfer-v100-sm70) | **verify before redistributing** |

**This repository contains no kernel source.** It is a record of what was done, what it measured,
and what did not work. Obtain the code from the upstream repositories above and check each licence
yourself.

## How the numbers here were checked

Every figure in this file is traceable to a line in `logs/`, and `claims.md` maps each claim to its
source line. The counts in [Integrity of the run](#integrity-of-the-run) are reproducible with:

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

The operational log format never contains prompts, generated text, request bodies or credentials —
which is why the raw logs could be published unredacted.

## Reproduce

1. Build NInfer for sm_70 (see the upstream repository; CUDA 12.x is required — CUDA 13 dropped
   Volta).
2. Apply the two kernel ports (companion repository for prefill; the tpx and Flo5k5 repositories
   above for decode).
3. Start the engine with the command line at the top of this file, arming
   `NINFER_SM70_ATTN_V2=1`. Raise `.wslconfig` to `memory=32GB` first — 14 GiB of pinned host KV
   does not fit in 16 GB together with the rest of the stack.
4. Drive it with any OpenAI-compatible client that keeps **one** stream. Compare against
   `logs/done-lines-raw.txt`.
