# 一张 2017 年的 V100，跑 2026 年的 27B 长上下文 agent

单卡 **Tesla V100-SXM2-32GB（sm_70）** + **Qwen3.8-27B**，在真实 agent 负载下量出来的**一套可用配置**，
以及支撑每个数字的原始引擎日志。完整仓库里没有一行内核是本机原创 —— 内核来自社区，这里交的是**把内核、调度、上下文缓存拼成能跑的样子**这件事本身。

> ### 先说两件事
>
> **① 这份内容被 AI 反复核验过很多轮，但 AI 难免还会有幻觉。**
> 这里每个数字都回溯到 `logs/` 里的原始日志，并且被**没有参与产出**的独立进程逐条重算过不止一次 —— 即便如此，
> **仍然可能有对不上的地方**（已经抓出过两轮，错在哪、怎么订正的都留在 [`claims.md`](claims.md) 末节）。
> 所以：**正文的转述万一和 `logs/` 里的原始行冲突，以原始行为准，别信我这里的总结。**
>
> **② 但实测效果是真的好，尤其是长上下文。**
> prompt 从 4 万涨到 20 万 token（约 5 倍深度），**解码中位数只从 56.8 掉到 46.6 tok/s（约 −18%）**，
> 全程没有塌陷式掉速；20 万 token 那一档仍稳定在 **42–52 tok/s**。
> 考虑到这是一张 2017 年的单卡、还是没人为它写新内核的 Volta 架构，**这个衰减幅度是这套配置最值钱的地方**。

**30 秒版**

| | |
|---|---|
| 解码速度 | **42.3 – 89.4 tok/s**（必须与 MTP 接受率成对读，见 §2） |
| 首字（TTFT） | 命中缓存 **0.54 – 7.7 秒**；未命中要全量预填，**43 秒 – 4 分 44 秒** |
| 稳定性 | 53 个真实请求：started 53 / done 53 / 400 零 / 503 零 / OOM 零 |
| 代价 | 14 GiB 页锁定主机内存；每轮上下文压缩后必然一次 2.5–4 分钟的全量重算 |
| 怎么抄 | [`launcher/start-ninfer.sh`](launcher/start-ninfer.sh) + [`launcher/wslconfig.example`](launcher/wslconfig.example)，四个关键参数见 §4 |
| 不要越的线 | prompt 约 **247,423 token** 是这张卡的硬顶，`--max-context` 别再往上抬（§5 第 1 条） |

---

## 关于作者（先看这一条，省得白问）

**我是这张卡的主人，也是这个仓库的所有者。我不读英文，也不写代码。** 这份文档和仓库里的文件都是 AI 帮我做的、帮我发的。

所以：**技术问题问我等于白问，我是真的不知道。** 请**问你自己手上那个 AI** —— 它能读这里的全部文件、`logs/` 里的原始日志、`claims.md` 里每条断言的来源映射，还有两个上游仓库，这些我都读不了。

也请友善一点：下面这些能跑通的配置，是用一堆跑失败的运行和大量干等换来的。

本文写成时间 2026-09-29。数字属于**这一台机器**，换机器别指望一样。英文版：[`README.en.md`](README.en.md)

---

## 1. 它解决什么问题

V100 是 2017 年的卡（Volta / sm_70 / 32 GB HBM2）。2026 年想拿它跑"现代"的 agent 负载，会撞三堵墙：

1. **新引擎不要它。** 主流推理栈的新注意力内核基本只写 sm_80 以上；Volta 要么没有内核，要么退化到很慢的路径。V100 的算力还在（SXM2 约 900 GB/s 带宽），但没人给它写新代码。
2. **27B dense + 长上下文装不下。** KV cache 随 token 线性涨，20 万 token 在 32 GB 卡上要一 MiB 一 MiB 地抠。
3. **agent 负载不是跑分。** 一个回合要装下系统提示 + 47 个工具 schema + 全部历史，prompt 常在十几万 token；而客户端会在窗口 80% 处自动压缩上下文 —— **压缩一发生，前面所有缓存全废，从头预填**。这就是"用着用着突然卡住五分钟"的来源。

这套配置把三堵墙各自绕过去：

- **① 移植内核**：把社区已公开的两个 sm70 内核搬进来（**预填**在配套仓库，**解码**在本仓库记录），全部有上游出处（§8）。
- **② 调对调度与上下文缓存**：四个参数按这张卡重新定值（§4），这一步是"能跑"和"跑得顺"的分界线。
- **③ 用真实负载量**：53 个请求来自一个真实 agent 会话（27B 自己把上下文长起来，自己触发压缩），不是合成语料跑分。

顺带一个反过来的结论：**这套栈上单报一个解码数字没有意义**。解码与 MTP 接受率不独立，只挑好看的行说"最快"是自欺（§2 末）。

**预填那一半在配套仓库**：[`taskeee/ninfer-v100-splitd-kernel`](https://github.com/taskeee/ninfer-v100-splitd-kernel) 覆盖预填内核的移植（1CatAI Split-D D256，+36~41%、首字 −3 分钟）；本仓库覆盖**解码内核、调度与上下文缓存、以及真实 agent 负载下的端到端表现**。

---

## 2. 效果

### 2.1 一个真实会话，53 个引擎请求

同一台机器、同一个 agent 会话、单流。27B 模型自己把上下文长到 20 万 token 并触发 3 轮压缩。
下表**每档挑一行**展示（完整 53 行逐行原文在 [`logs/done-lines-raw.txt`](logs/done-lines-raw.txt)）。

| req | prompt | 缓存% | 复用来源 | TTFT | 预填 tok/s | **解码 tok/s** | **MTP 接受率** |
|---:|---:|---:|---|---:|---:|---:|---:|
| 3 | 40,119 | 0.0 | root | 43.1 s | 1,000 | 55.5 | 49.0% |
| 7 | 49,540 | 99.7 | private endpoint | 0.71 s | 203.0 | 59.2 | 56.2% |
| 9 | 48,880 | 89.2 | turn closure | 7.3 s | 728.6 | 51.6 | 43.0% |
| 14 | 65,536 | 100.0 | private endpoint | 1.9 s | 14.2 | 56.0 | 50.5% |
| 24 | 88,096 | 96.9 | private endpoint | 4.7 s | 602.2 | 47.2 | 42.8% |
| 32 | 98,612 | 99.9 | private endpoint | 4.5 s | 11.9 | **89.4** | **83.1%** |
| 33 | 88,528 | 0.0 | root（探针） | 1 m 46.8 s | 829.8 | 72.4 | 94.4% |
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

**怎么读这张表：**

- **解码必须与接受率成对读**，两者不独立：表里最慢的两行（42.3 / 44.9）接受率就是最低的 51.3% / 45.7%。
- **不要把个别高值当"最快"**：本次会话真正的解码高值是 req#32 = 89.4（接受 83.1%）、req#8 = 75.1（72.5%）、req#33 = 72.4（94.4%）、req#29 = 71.1（75.6%）、req#23 = 70.1（69.2%）—— 其中 #8/#29/#23 **不在上表里**（上表每档只挑了一行）。
- **预填那一列的极值没有解释力**：深度浅、增量只有几十 token 的轮次分母极小，会算出 1000 或 7.0 tok/s 这种数。**TTFT 才是可读的量。**
- **「复用来源」列有两处要说明**：命中时引擎日志会打印 `private endpoint` / `turn closure` / `shared prefix` 路径标签；**未命中时不打印任何标签，只打印 `cache 0 (0.0%)`**。表里的 `root` 是按"未命中"加注的（`root` 是引擎文档里该路径的正式名字），`root（探针）` 里的"探针"依据来自被测会话自己的台账，**不是引擎日志**。
- 第 40、45、48 行是**客户端压缩摘要调用**（判定依据 `max output 8,192` 全文只出现 3 次 + 三条紧跟越阈请求晚 0.12 s / 3.87 s / 0.09 s + 消息数塌缩 104→73→38、49→32→24、29→25→12）。⚠️ **这是推断，不是日志事实** —— 引擎日志不记 prompt 内容、也没有 compaction 字段。旁证很强，但严格说是推断。

**汇总**（口径写在 [`claims.md`](claims.md)，可逐条重算）：

| 口径 | 值 |
|---|---|
| 解码（prompt ≥40k 的全部行） | 42.3 – 89.4 tok/s |
| MTP 接受率（同口径） | 42.8 – 94.4% |
| 缓存命中（复用 ≥99%）的行 TTFT | 0.54 s – 7.7 s（n=21） |
| 缓存未命中、真实深度（prompt ≥40k） | 53 个请求里 **9 个**，TTFT 43.1 s – 4 m 44.2 s |
| 整场完整性 | `started 53 / done 53 / 400 零 / 503 零 / OOM 零 / FATAL 零`（引擎 pid 24，采集时采样） |

### 2.2 深度与接受率：区间怎么读

⚠️ 本节 2026-09-29 被独立核对推翻过一次（4 行里错 3 行），现在是按逐行原值重写的版本。
**区间数字一律以 2.1 的逐行原值为准，本节只回答"这段里都有谁 + 真实 min/max"。**

| 区间（含哪些 req） | n | 解码 tok/s | 预填 tok/s | MTP 接受率 |
|---|---:|---|---|---|
| ≤167k（prompt 40k–167,428，排除 3 条摘要） | 42 | **44.9 – 89.4** | 10.5 – 1000 | **42.8 – 94.4%** |
| 175k–206k（#39 #43 #44 #47 #53） | 5 | **42.3 – 52.1** | 7.0 – 616.1 | 51.3 – 65.2% |
| 压缩后 113k–138k（#41 #46 #49 #50） | 4 | **44.9 – 58.4** | 429.8 – 756.0 | 45.7 – 66.2% |
| 压缩摘要调用（#40 #45 #48） | 3 | 58.5 – 67.4 | 648.7 – 799.6 | 67.3 – 69.1% |

**唯一站得住的深度结论**：175k–206k 那 5 行的解码（42.3–52.1）确实比浅层低；但**接受率不是一致地低** ——
5 行里有 3 行（#39 63.0% / #47 57.0% / #53 65.2%）**高于** ≤167k 那 42 行的中位数 **56.15%**，
而 ≤167k 那 42 行里也有 15 行低于 51.3%。**所以这不是干净的分离。**

⚠️ 早先版本在这里写"175k–206k 的接受率都比中位数 56.1% 低" —— **那是错的**，已删除。

**方向一致（越深越慢），但机制未确立**：现象与 KV 压力吻合（245k int8 KV 池、32 GB 设备、14 GiB 主机卸载），但没有收集反证。
**把原因当未知，把观测当实测。**

### 2.3 内核 A/B（解码）

同一台机器、同一 prompt（170,607 token）、`--greedy`、K=3、int8 KV。每臂取 `long-cold` 那条，原始 JSON 在 [`evidence/v2ab/`](evidence/v2ab/)。

| 臂 | 文件 | 解码 tok/s | MTP 接受率 |
|---|---|---:|---:|
| 原版内核，`--spec mtp` | `v2ab-v2off-200k.json` | 32.5653 | 0.5209 |
| 移植 v2 内核，`--spec mtp` | `v2ab-flo-v2-200k.json` | **59.1960** | 0.7431 |
| 原版内核，`--spec none` | `v2ab-v2off-nospec-200k.json` | 15.2077 | — |
| 移植 v2 内核，`--spec none` | `v2ab-flo-nospec-v2-200k.json` | **21.8427** | — |

**`--spec none` 那一对才是诚实口径**：开着投机解码时两个臂生成的内容会分叉（浮点累加顺序不同），接受率因此不同，看起来的一部分收益并非来自内核。
无接受率干扰口径：**15.2077 → 21.8427 = +43.6%**（全精度比值 `21.842699455932266 / 15.20774511610815 - 1 = 0.436287844…`）。

### 2.4 压缩的真实代价（每轮都不同，别用一个平均数概括）

客户端在声明的 245k 窗口 80% 处压缩，本次会话触发 3 轮：

| 轮 | 会话 prompt | 摘要调用 | 压缩后第一条 | 恢复 |
|---|---|---|---|---|
| 1 | req#39 · 201,700 | req#40 · 81,919 → 输出 4,209 · 1 m 53.6 s · 67.4 tok/s · 缓存 59.7% | req#41 · 136,497 · **缓存 0%** · TTFT 3 m 20.2 s | req#42 · 98.5% |
| 2 | req#44 · 206,364 | req#45 · 88,228 → 输出 2,773 · 2 m 33.1 s · 66.3 tok/s | req#46 · 138,406 · **缓存 0%** · TTFT 3 m 24.0 s | — |
| 3 | req#47 · 183,938 | req#48 · 136,960 → 输出 4,491 · 4 m 37.1 s · 58.5 tok/s | req#49 · 113,562 · **缓存 0%** · TTFT 2 m 30.9 s | req#50 · **99.4%**，TTFT 1.8 s |

| 轮 | 生成摘要 | 压后重新预填 | 合计 |
|---|---:|---:|---:|
| 1 | 1 m 53.6 s | 3 m 20.2 s | **5 m 13.8 s** |
| 2 | 2 m 33.1 s | 3 m 24.0 s | **5 m 57.1 s** |
| 3 | 4 m 37.1 s | 2 m 30.9 s | **7 m 8.0 s** |

**压缩后立刻 `cache 0%` 是设计行为，不是 bug**：NInfer 官方文档写明*每个检查点都会使"从第一个被替换的历史 token"起的复用失效*，而摘要是插在会话最前面的，所以它之前的几乎全部内容都无法复用。
**加内存解决不了这件事 —— 前缀是真的变了。**

两个待解观察：第 1 轮的摘要调用复用了 59.7% 前缀，第 2、3 轮报 0%（**原因未确立**）；第 3 轮触发时提供方报的 prompt 是 183,938，低于 196,000 的标称阈值 —— 客户端的压力计量对密排 ASCII 用字符启发式估算（该形状实测约 1.35 字符/token，启发式按 4 字符/token 算），**所以"阈值 196,000"是标称值，不是硬边界**（此解释来自客户端台账，不是本仓库日志能证明的）。

---

## 3. 怎么装、怎么跑

### 3.1 前提

| 项 | 本次实测环境 |
|---|---|
| GPU | **Tesla V100-SXM2-32GB**（sm_70），采集时 31,522 / 32,768 MiB（96.2%），33 °C |
| 第二张卡 | RTX 3080 Ti，仅驱动显示，约 800 MiB |
| 宿主 | **63.15 GiB（67.8 GB）内存**；WSL2 `Ubuntu-24.04`；`.wslconfig`：`memory=32GB`、`swap=8GB`、`networkingMode=nat` |
| 引擎 | NInfer `build-v100/apps/ninfer-serve`，299,287,880 字节，md5 `6b104a4464cdab6687351c00770d7ba8`（2026-09-28 22:13:04 +0800） |
| 模型 | `qwen3_8_27b_nvfp4.ninfer`，对外名 `qwen3.8-27b-uncen` |
| 客户端 | DeepSeek Harness（DSH）网页端，47 个工具 schema，**单流** |
| CUDA | **12.x**（**CUDA 13 已经不支持 Volta**） |

### 3.2 四步

1. **为 sm_70 构建 NInfer**（见上游仓库 [`geoffwatts/ninfer-v100`](https://github.com/geoffwatts/ninfer-v100)）。
2. **打上两处内核移植**：预填见配套仓库 [`ninfer-v100-splitd-kernel`](https://github.com/taskeee/ninfer-v100-splitd-kernel)；解码见 §8 的 tpx 与 Flo5k5 两个上游仓库。
3. **放 `.wslconfig` 并重启 WSL**：样例在 [`launcher/wslconfig.example`](launcher/wslconfig.example)。**必须先把内存抬到 32GB** —— 14 GiB 页锁定 host KV 加上其余部分，16 GB 装不下。改完 `wsl --shutdown`。
4. **用启动脚本起引擎**：现成可跑的版本在 [`launcher/start-ninfer.sh`](launcher/start-ninfer.sh)（顶部三个变量改掉即可），环境变量 `NINFER_SM70_ATTN_V2=1` 启用 v2 解码内核。

引擎命令行（启动脚本里的就是这个）：

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

### 3.3 起来以后应该看到这些行（对不上就别往下走）

原文在 [`logs/startup-raw.txt`](logs/startup-raw.txt)：

```
weights ready      | 20.0 GiB | 1m 3.6s | 322.3 MiB/s
pinning host state | 1.72 GiB
host state pinned  | 1.72 GiB | 1.5s
pinning host KV    | 14.0 GiB
host KV pinned     | 14.0 GiB | 12.0s
engine ready | qwen3.8-27b/nvfp4 | total 1m 26.3s | weights 20.0 GiB
capacity | KV 245,056 tokens, int8, explicit | pages 3,829/3,829 | runtime 10.5 GiB | free 188.3 MiB
context cache | 1 active + 1 cached device states | host 12 states, 14.0 GiB KV | private 4 | shared 8 | anchors 8
```

**如果 `pinning host KV` 不是 14.0 GiB，或者进程正好死在这一行（`cudaMallocHost failed: cudaErrorMemoryAllocation`）**，把 `--host-kv-mib` 往下调 —— 见 §5 第 2 条：**上限是单次分配上限，不是"内存还剩多少"。**

### 3.4 客户端

任何 OpenAI 兼容客户端都能驱动它，**保持单流**（`--max-concurrency 1` 是刻意选择，见 §5 第 6 条）。
拿 [`logs/done-lines-raw.txt`](logs/done-lines-raw.txt) 对照自己的数字即可。

---

## 4. 四个关键设置，为什么是这些值

| 设置 | 原版默认 | 本机使用 | 依据 |
|---|---:|---:|---|
| `--host-state-slots` | 8 | **12** | 依据来自**引擎源码**（`src/targets/qwen3_6/impl/runtime/program_impl.h`）：`logical_state_capacity = (max_concurrency + device_state_slots) + host_state_slots`，而地址空间是 `max_private_continuations + max_shared_prefixes + 1`。取默认计数（4/8）时为 13，而 state image 只有 (1+1)+8 = 10 个 ⇒ 多出来的检查点无法落地。2 + 12 = 14 ≥ 13。**这两个计数与源码行号不在本仓库的日志证据里**，属源码级依据；只有"每槽约 147 MiB 页锁定内存"可由日志反算（`pinning host state \| 1.72 GiB` ÷ 12）。 |
| `--host-kv-mib` | 8192 | **14336** | 可复用跨请求前缀的**字节池**。按约 45 KiB/token 算，8192 MiB ≈ 18.7 万 token，不足一个 245k 窗口。**上限不是内存大小**：本机 CUDA 探针实测**单次** `cudaMallocHost` 上限约 15 GiB（16 GiB 即 `cudaErrorMemoryAllocation`），而累计 2 GiB 小块能到 28 GiB；引擎是一次性分配，所以约 15 GiB 就是硬顶，且**与 `.wslconfig` 给多少内存无关**（32 GB 与 40 GB 下测得完全相同）。试过 20 GiB：引擎起不来。 |
| `--pending-timeout-ms` | 30000 | **900000** | "准备 + 排队"的绝对截止时间。用默认 30 秒时，任何第二个请求（子代理、辅助调用）会在排队超时后被**杀掉**（`HTTP 503 request_queue_timeout`），而不是等待。**等待只是慢，被杀是整轮作废。** |
| `--max-private-continuations` / `--max-shared-prefixes` / `--max-long-anchors-per-continuation` | 2 / 4 / 2 | **4 / 8 / 8** | 这三个是**描述符计数**，不占内存（`address_capacity = private + shared + 1`），调大不会挤小每个检查点的字节预算。 |

`--max-context` **没有**再往上抬。按引擎自己那次拒启的报数反推：
`12,004,767,744 ÷ 262,144 = 45,794.5547 B/token` ⇒ `11,330,617,856 ÷ 45,794.5547 ≈ 247,422.8`，
即这张卡上能准备的 prompt 上限约 **247,423 token** —— 所以 `245000` 只剩约 2,400 token 余量。

**第二个来源方向一致，但精度有限**：正在跑的引擎自己那行 `KV 245,056 tokens … runtime 10.5 GiB`，
按 45,794.5547 B/token 算得 10.4515 GiB，四舍五入正好印成 `10.5 GiB`；反过来，`10.5 GiB` 这个两位有效数字
只能把每 token 成本钉在约 45,788–46,226 区间内 —— **对得上，但别当独立证明用。**

试过 `262144`，引擎拒启：`requested Engine runtime reservation requires 12004767744 bytes, but only 11330617856 bytes are available`。
⚠️ **这一处早先版本写错并已订正**：原来把 `45,794`（整数）与 `45,794.55` 混用，并把硬顶写成 `≈247,428`，还附了一句"取整数分母的近似"来圆它 —— **`247,428` 在任何分母下都算不出来**（除以 45,794 得 247,425.8，取整是 247,426），那句解释也是编的。现全文统一为 `45,794.5547 B/token` / **≈247,423**。
这两行来自启动器控制台（对应引擎日志已被后一次成功启动覆盖），原文见 [`evidence/failed-startup-console.txt`](evidence/failed-startup-console.txt)。

---

## 5. 坑（按踩到的顺序）

1. **247k 硬墙可撞，且引擎侧无解。** `--max-context 245000` 卡的是**准备后**的 prompt（系统提示 + 工具 schema + 全部历史）。一条超大工具结果能一步顶穿；而当"最新那个不可分单元"本身就太大时，客户端压缩和 NInfer 的溢出恢复都救不了。
2. **约 15.72 GiB 页锁定主机内存是前缀复用的价格**（14.0 GiB host KV + 1.72 GiB host state，两者都由 `startup-raw.txt` 的 `pinning host` 行给出）。`--no-prefix-reuse` 能把它降到零，代价是每轮都全量预填。**单次分配上限约 15 GiB，且不随 WSL 内存增长** —— 这条结论的数据未随本仓库发布（方法与说明见 [`evidence/pinned-probe-notes.txt`](evidence/pinned-probe-notes.txt)）。
3. **压缩后必然一次全量预填，加内存没用**（前缀真的变了，见 §2.4）。这是"用着用着卡五分钟"的真身。
4. **引擎静默死过一次，原因从未查明。** 一次 193k 改写请求之后：客户端 `RemoteDisconnected`，日志停在预填中段，**没有任何报错行**，当时设备侧只剩 188 MiB。复现一次。**无日志行的静默死亡是这套方案最糟的失效形态。**
5. **移植内核 ≠ 逐 token 等价。** 解码内核改变了浮点累加顺序，长深度 greedy 输出**会与移植前分叉**，token 级等价从未被证明（上游内核自测在两档开关下都通过，但那不是同一个断言）。
6. **`--max-concurrency 1` 是刻意选择**：KV 池只按一条序列排量，深度下第二个流服务不了。NInfer 文档里 `--max-concurrency` 合法范围是 1..8 —— 这是容量问题，不是开关限制。
7. **启动器只能留一份。** 本机为此出过两次事故：一次修复落到了过期副本上；第二次那个副本悄悄丢掉了 `--vision`，于是所有带图回合 400 `vision_disabled`。**权威文件只有一个，别的名字都是错的。**
8. **引擎日志每次重启即截断、无轮转**（`/home/ai/ninfer-serve.log`）。要引用某次启动的数字，必须在重启前先抄出来。
9. **Windows 侧写脚本：`.ps1` 里一个非 ASCII 字符都不能有**（中文路径会变乱码导致找不到、字符串里带 `≥` `–` 会让整脚本解析失败）。脚本体保持纯 ASCII，中文外置成 UTF-8 文件读进来。
10. **数字属于一台机器。** SXM2（约 900 GB/s）而非 PCIe（约 780 GB/s）、63.15 GiB 宿主、单流、单一模型制品。换机器别指望数字不变。

---

## 6. 试过但没用的东西（省得你再走一遍）

⚠️ **`[未随证据发布]` —— 本节没有任何一条能追到 `logs/`。** 它来自本机未发布的引擎台账与 bash 语义。

- `--kv-dtype fp8` —— 预填 −88%、解码 −88%，TTFT 12.7 s → 1 m 50 s。Volta 没有原生 fp8 路径，会退回逐元素反量化。
- `--kv-dtype nvfp4` / `k8v4` —— **Volta 直接拒收**：32 毫秒内 `FATAL ... NVFP4 KV-cache storage is unavailable on Volta`。**这张卡上没有办法把 KV 容量翻倍。**
- `--prefill-chunk 8192` —— 预填 −41%。1024 在浅层略差、深层打平。`2048` 是实测最优。
- `--media-cache-mib` / `--media-live-mib` —— 这两个是**上限，不是预分配**；改它不改变显存也不改变速度。
- 上调 `--max-context` —— 见 §5 第 1 条，卡扛不住。
- **跑子代理 / 第二个并发流** —— 第二个请求会排队等一次 40–170 秒的预填，在默认 `--pending-timeout-ms 30000` 下被 `HTTP 503` 杀掉。**要改的是超时，不是显存。**
- 启动器里写 `exec VAR=1 cmd` —— bash 会把赋值当程序名。赋值必须写在 `exec` **之前**。
- **想靠加内存换更大的前缀池** —— 单次 `cudaMallocHost` 上限约 15 GiB 且与 WSL 内存无关（§5 第 2 条）。

---

## 7. 证据在哪，以及哪些追不到

**能逐行复现的**（每个数字 → 原始行）：

| 内容 | 位置 |
|---|---|
| 53 行逐行主表原文 | [`logs/done-lines-raw.txt`](logs/done-lines-raw.txt) |
| 每条请求的 started 行（消息数、max output、thinking 档） | [`logs/req-events-raw.txt`](logs/req-events-raw.txt) |
| 启动与环境（nvidia-smi、命令行、二进制 md5、WSL 内存） | [`logs/startup-raw.txt`](logs/startup-raw.txt)、[`logs/environment-raw.txt`](logs/environment-raw.txt) |
| 完整引擎日志快照（07:31 那次成功启动之后） | [`logs/ninfer-serve.log.snapshot-final`](logs/ninfer-serve.log.snapshot-final) |
| 被测会话自己的台账 | [`logs/under-test-ledger.md`](logs/under-test-ledger.md) |
| 内核 A/B 的四个原始臂（10 个 JSON） | [`evidence/v2ab/`](evidence/v2ab/) |
| 上游身份核对 | [`logs/upstream-identity.txt`](logs/upstream-identity.txt) |
| **每条断言 → 来源行 + 核对命令 + 期望值** | [`claims.md`](claims.md) |

**追不到 `logs/` 的四类**（正文里已逐条标 `[未随证据发布]`，`claims.md` 有完整清单）：

1. **内核单次调用耗时**（1.637 → 0.689 ms 中位，n=101）—— 来自本机另一份 trace 分析，`logs/` 与 `evidence/` 里没有这份数据；
2. **两次失败启动的 FATAL 行** —— 来自启动器控制台，对应引擎日志已被后一次成功启动覆盖；
3. **页锁定内存探针**（单次 15 GiB / 累计 28 GiB）—— 只有方法与说明，没有原始输出；
4. **§6「试过但没用的东西」整节** —— 来自未发布的引擎台账。

另外两处**二手或单点**的：`峰值 31,522 MiB` 其实只有**一个** nvidia-smi 采样点，严格说是某时刻值；`WSL2 Ubuntu-24.04` 的名称来自启动器与 `.wslconfig`，机器输出未随仓库发布。

**本文被审过。** 发布后由一个**没有参与产出**的独立进程逐条重算过全部断言，第一遍就找出 19 处对不上（**全部集中在归纳/派生表述，原始行 0 处编造**），订正内容与残余问题在 [`claims.md`](claims.md) 末节。
**结论：原始行可信，归纳层要小心 —— 凡涉及区间的数字，请回到逐行原值自己重算。**

---

## 8. 署名与许可

本方案里**没有任何内核是本机所有者的原创工作**。

| 组件 | 来源 | 许可 |
|---|---|---|
| NInfer 引擎 | [geoffwatts/ninfer-v100](https://github.com/geoffwatts/ninfer-v100) | Apache-2.0（见该仓库） |
| Split-D D256 预填内核 | [fishlikeX/sm70-attn](https://github.com/fishlikeX/sm70-attn) | MIT（见配套仓库） |
| `small_t_i8_volta_v2.cuh` 解码内核 | [huangserva/ninfer-v100-tpx](https://github.com/huangserva/ninfer-v100-tpx) | Apache-2.0 |
| 六个 sm70 提交 | [Flo5k5/ninfer-v100-sm70](https://github.com/Flo5k5/ninfer-v100-sm70) | Apache-2.0（**再分发前请自行核实**） |

**本仓库不含任何内核源码，也不含模型制品。** 它只是一份记录：做了什么、量到了什么、什么没用。
代码请从上面这些上游仓库获取，并自行核对各自许可。[`launcher/`](launcher/) 里只有启动脚本与 `.wslconfig` 样例 —— 那些是配置，不是内核代码。
