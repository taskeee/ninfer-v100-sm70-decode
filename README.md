# 单卡 Tesla V100（sm_70）跑 NInfer：sm70 解码内核 + 上下文缓存调参，附 53 个真实 agent 请求的满载实测

在一张 **Tesla V100-SXM2-32GB** 上，用 [NInfer](https://github.com/geoffwatts/ninfer-v100) 跑 27B dense 模型的一套可用组合，**以及本文每一个数字背后的原始日志**。

配套仓库：[`ninfer-v100-splitd-kernel`](https://github.com/taskeee/ninfer-v100-splitd-kernel) 覆盖**预填**侧（1CatAI Split-D D256）。
本仓库覆盖**解码**侧、调度与上下文缓存设置，以及真实 agent 负载下的端到端表现。

---

## 关于这个仓库

**本文由 AI 代发。** 机器的所有者不读英文、也不写代码。他要的是：同样卡着这张卡的人现在没路可走，把这套东西写出来给他们抄。**他回答不了技术问题** —— 有疑问请**问你自己手上的 AI**，它能读这里的文件、`logs/` 下的原始日志和两个上游仓库，这些他都读不了。请友善一点：这里面能跑通的东西，是他用一次次失败的运行和大量等待换来的。

---

## 这里有什么

| 内容 | 位置 |
|---|---|
| 53 个真实 agent 请求的满载实测（表） | 本文件「实测结果」一节 |
| 每个数字对应的原始日志行 | [`claims.md`](claims.md) |
| 原始引擎日志（未加工副本） | [`logs/`](logs/) |
| 内核数字背后的 A/B 原始臂 | [`evidence/v2ab/`](evidence/v2ab/) |

英文版：[`README.en.md`](README.en.md)

---

## 测试机

| 项 | 值 |
|---|---|
| GPU | **Tesla V100-SXM2-32GB**（sm_70），峰值 31,522 / 32,768 MiB（96.2%），采集时 33 °C |
| 第二张卡 | RTX 3080 Ti，仅驱动显示，全程约 800 MiB |
| 宿主 | 63.1 GB 内存，WSL2 Ubuntu-24.04，`.wslconfig`：`memory=32GB`、`swap=8GB`、`networkingMode=nat` |
| 引擎 | NInfer `build-v100/apps/ninfer-serve`，299,287,880 字节，md5 `6b104a4464cdab6687351c00770d7ba8`（2026-09-28 22:13:04 +0800） |
| 模型 | `qwen3_8_27b_nvfp4.ninfer`，对外名 `qwen3.8-27b-uncen` |
| 客户端 | DeepSeek Harness（DSH）网页端，47 个工具 schema，**单流** |

引擎命令行：

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

环境变量：`NINFER_SM70_ATTN_V2=1`。
启动记录（原文，见 `logs/startup-raw.txt`）：

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

---

## 相对原版 NInfer V100 构建，改了什么

其中三项是**对已公开 sm70 内核的移植**，这套方案里没有任何内核代码是本机原创。第四项是配置。

1. **解码注意力内核** —— 来自 [huangserva/ninfer-v100-tpx](https://github.com/huangserva/ninfer-v100-tpx)（Apache-2.0）的
   `small_t_i8_volta_v2.cuh`，编入并用 `NINFER_SM70_ATTN_V2=1` 启用。8 warp / Bc=64：每个 warp 只算自己 8 个 key 的
   QK^T，而不是 4 个 warp 把同一份 16 key 的 QK^T+softmax 重算 4 遍；行最大值通过共享内存交换 ——
   每 64 个 key 同步 3 次，原版 8 次。
2. **Flo5k5/ninfer-v100-sm70 的六个 sm70 提交**（同一基座 fork）：int8 split-K QK^T、fp16 magic-bias 反量化、
   MTP W8 GEMV、GDN 融合 norm+gating 内核、以及一处 3 行的 T=4 WAR 竞态修正（原树带这个隐患）。
3. **预填** —— 在配套仓库里，本文不重复。
4. **调度与上下文缓存设置** —— 见下节。

### 这四个设置为什么这么定

| 设置 | 原版默认 | 本机使用 | 依据（实测） |
|---|---:|---:|---|
| `--host-state-slots` | 8 | **12** | `logical_state_capacity = (max_concurrency + device_state_slots) + host_state_slots`。可寻址检查点是 4 private + 8 shared + 1 = 13，而 state image 只有 10 个 ⇒ 多出来的检查点无法落地。2 + 12 = 14 ≥ 13。代价是每槽约 147 MiB **页锁定**主机内存。 |
| `--host-kv-mib` | 8192 | **14336** | 可复用跨请求前缀的**字节池**。按约 45 KiB/token 算，8192 MiB ≈ 18.7 万 token，不足一个 245k 窗口。**上限不是内存大小**：本机 CUDA 探针实测**单次** `cudaMallocHost` 上限为 15 GiB（16 GiB 即 `cudaErrorMemoryAllocation`），而**累计** 2 GiB 小块能到 28 GiB。引擎是一次性分配，所以约 15 GiB 就是硬顶，且**与 `.wslconfig` 给多少内存无关**（32 GB 与 40 GB 下测得完全相同）。试过 20 GiB：引擎起不来，`cudaMallocHost failed: cudaErrorMemoryAllocation`。 |
| `--pending-timeout-ms` | 30000 | **900000** | 「准备 + 排队」的绝对截止时间。用默认 30 秒时，任何第二个请求（子代理、辅助调用）会在排队超时后被**杀掉**（`HTTP 503 request_queue_timeout`），而不是等待。等待只是慢，被杀是整轮作废。 |
| `--max-private-continuations` / `--max-shared-prefixes` / `--max-long-anchors-per-continuation` | 2 / 4 / 2 | **4 / 8 / 8** | 这三个是**描述符计数**，不占内存（`address_capacity = private + shared + 1`），调大不会挤小每个检查点的字节预算。 |

`--max-context` **没有**上调。实测硬顶是 `11,330,617,856 B ÷ 45,794 B/token ≈ 247,428 token`，
所以 `245000` 只剩约 2,400 token 余量。试过 262144，引擎拒启：
`requested Engine runtime reservation requires 12004767744 bytes, but only 11330617856 bytes are available`。

---

## 实测结果：真实 agent 负载

**一个连续会话、53 个引擎请求**，27B agent 自己把上下文长起来、并触发客户端自动压缩循环。
**这不是合成跑分**，每一行都是一次真实 agent 回合。原始行见 `logs/done-lines-raw.txt`。

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

第 40、45、48 行是**压缩摘要调用**（特征是 `max output 8,192`，客户端摘要输出上限的默认值），
它们同样是引擎的工作，所以列出。

**解码速度必须与接受率成对读。** 两者不独立：最慢的几行（42.3 / 44.9 / 46.4）接受率都在 45–55%，
最快的几行（89.4 / 67.4 / 66.3）在 68–83%。**在这套栈上，单报一个解码数字没有意义。**

汇总：**缓存命中（复用 ≥99%）的行，TTFT 0.54 – 7.7 秒。**
**缓存未命中（`cache 0.0%`，真实深度下 53 个请求里有 9 个）的行，TTFT 43 秒 – 4 分 44 秒** ——
因为整个 prompt 要重新预填（`TTFT ≈ prompt ÷ 预填速度`）。

### 这次运行的完整性

```
started  = 53      done = 53
rejected = 0       failed = 0
HTTP 503 = 0       HTTP 400 = 0
OOM / CUDA 错误 = 无
引擎进程数 = 全程 1
```

### 深度表现

| 深度区间 | 解码 | 预填 | MTP 接受率 |
|---|---|---|---|
| ≤ 167k | 53 – 58 tok/s | 616 – 799 tok/s | 59 – 69% |
| 175k – 206k | **42 – 47 tok/s** | **422 – 444 tok/s** | **51 – 57%** |
| 压缩后回到 113k – 138k | 57 – 58 tok/s | 685 – 756 tok/s | 63 – 67% |
| 压缩摘要调用（82k – 137k） | 58 – 67 tok/s | 649 – 800 tok/s | 67 – 69% |

175–206k 区间三项指标同时下降，压缩之后恢复。**机制未确立** —— 现象与 KV 压力吻合
（245k int8 KV 池、32 GB 设备、14 GiB 主机卸载），但没有收集反证。**把原因当未知，把观测当实测。**

---

## 压缩循环（3 轮，全部实测）

客户端在声明的 245k 窗口的 80% 处压缩。共触发 3 轮，每轮在引擎日志里都表现为一条
`max output 8,192` 的摘要请求。

| 轮 | 会话 prompt | 摘要调用 | 之后 | 恢复 |
|---|---|---|---|---|
| 1 | req#39 · 201,700 | req#40 · 81,919 → 输出 4,209 · 1 m 53.6 s · 67.4 tok/s · 缓存 59.7% | req#41 · 136,497 · **缓存 0%** · TTFT 3 m 20.2 s | req#42 · 98.5% |
| 2 | req#44 · 206,364 | req#45 · 88,228 → 输出 2,773 · 2 m 33.1 s · 66.3 tok/s | req#46 · 138,406 · **缓存 0%** · TTFT 3 m 24.0 s | — |
| 3 | req#47 · 183,938 | req#48 · 136,960 → 输出 4,491 · 4 m 37.1 s · 58.5 tok/s | req#49 · 113,562 · **缓存 0%** · TTFT 2 m 30.9 s | req#50 · **99.4%**，TTFT 1.8 s |

压缩之后立刻 `cache 0%` **是设计行为，不是 bug**：NInfer 官方文档写明
*每个检查点都会使从第一个已替换历史 token 起的复用失效*，而摘要是插在会话最前面的，
所以它之前的几乎全部内容都无法复用。**每轮压缩请预留约 5 分钟**（生成摘要 ≈2 分钟，
重新预填压缩后的历史 ≈3 分钟）。**加内存解决不了这件事。**

一条观察，**原因未确立**：第 1 轮的摘要调用复用了 59.7% 的会话前缀，第 2、3 轮报的是 0%。

---

## 内核 A/B 数字（解码）

同一台机器、同一 prompt（170,607 token）、`--greedy`、K=3、int8 KV。原始臂在 `evidence/v2ab/`；
每个臂取 `long-cold` 那一条。

| 臂 | 文件 | 解码 tok/s | MTP 接受率 |
|---|---|---:|---:|
| 原版内核，`--spec mtp` | `v2ab-v2off-200k.json` | 32.5653 | 0.5209 |
| 移植 v2 内核，`--spec mtp` | `v2ab-flo-v2-200k.json` | **59.1960** | 0.7431 |
| 原版内核，`--spec none` | `v2ab-v2off-nospec-200k.json` | 15.2077 | — |
| 移植 v2 内核，`--spec none` | `v2ab-flo-nospec-v2-200k.json` | **21.8427** | — |

**`--spec none` 那一对才是诚实口径**：开着投机解码时，两个臂生成的内容会分叉（浮点累加顺序不同），
接受率因此不同，看起来的一部分收益并非来自内核。无接受率干扰口径：**15.2077 → 21.8427 = +43.6%。**
解码内核单次调用本身，在 ≥10 万 key 的窗口下实测 **1.637 ms → 0.689 ms 中位（2.38×，每臂 n=101）**。

---

## 已知边界与未验证项 —— 依赖本文任何内容之前请先读这一节

1. **移植内核的逐字节一致性未验证。** 解码内核改变了浮点累加顺序，所以长深度 greedy 输出
   **会与移植前分叉**。token 级等价从未被证明。上游内核自测在两档开关下都通过，但那不是同一个断言。
2. **引擎静默死过一次。** 一次 193k 改写请求之后：客户端 `RemoteDisconnected`，日志停在预填中段，
   **没有任何报错行**，当时设备侧只剩 188 MiB。复现一次，原因从未查明。
   **无日志行的静默死亡是这套方案最糟的失效形态。**
3. **245k 硬墙可撞，且引擎侧无解。** `--max-context 245000` 卡的是**准备后**的 prompt
   （系统提示 + 工具 schema + 全部历史）。一条超大工具结果能一步顶穿，而当"最新那个不可分单元"
   本身就太大时，客户端压缩和 NInfer 的溢出恢复都救不了。实测硬顶约 247,428 token。
4. **约 9.7 GiB 页锁定主机内存是前缀复用的价格**（14.0 GiB host KV + 1.72 GiB host state）。
   `--no-prefix-reuse` 能把它降到零，代价是每轮都全量预填。**单次分配上限约 15 GiB，且不随 WSL 内存增长** ——
   见上表。
5. **数字属于一台机器。** SXM2（约 900 GB/s）而非 PCIe（约 780 GB/s）、63 GB 宿主、单流、单一模型制品。
   换机器别指望数字不变。
6. **175–206k 的掉速没有确立原因**（见上）。
7. `--max-concurrency 1` 是刻意选择：KV 池只按一条序列排量。深度下第二个流服务不了。
   NInfer 文档里 `--max-concurrency` 合法范围是 1..8 —— 这是容量问题，不是开关限制。

## 试过但没用的东西（省得你再走一遍）

- `--kv-dtype fp8` —— 预填 −88%、解码 −88%，TTFT 12.7 s → 1 m 50 s。Volta 没有原生 fp8 路径，
  会退回逐元素反量化。
- `--kv-dtype nvfp4` / `k8v4` —— **Volta 直接拒收**：32 毫秒内
  `FATAL ... NVFP4 KV-cache storage is unavailable on Volta`。**这张卡上没有办法把 KV 容量翻倍。**
- `--prefill-chunk 8192` —— 预填 −41%。1024 在浅层略差、深层打平。`2048` 是实测最优。
- `--media-cache-mib` / `--media-live-mib` —— 这两个是**上限，不是预分配**；改它不改变显存也不改变速度。
- 上调 `--max-context` —— 见边界第 3 条，卡扛不住。
- **跑子代理 / 第二个并发流** —— 第二个请求会排队等一次 40–170 秒的预填，在默认
  `--pending-timeout-ms 30000` 下被 `HTTP 503` 杀掉。**要改的是超时，不是显存。**
- 启动器里写 `exec VAR=1 cmd` —— bash 会把赋值当程序名。赋值必须写在 `exec` **之前**。
- **两个启动器文件、只有一个是真的** —— 本机为此出过两次事故（一次修复落到了过期副本上，
  第二次它悄悄丢掉了 `--vision`，于是所有带图回合 400 `vision_disabled`）。
  **只保留一份权威启动器。**

## 署名与许可

本方案里没有任何内核是本机所有者的原创工作。

| 组件 | 来源 | 许可 |
|---|---|---|
| NInfer 引擎 | [geoffwatts/ninfer-v100](https://github.com/geoffwatts/ninfer-v100) | 见该仓库 |
| Split-D D256 预填内核 | [fishlikeX/sm70-attn](https://github.com/fishlikeX/sm70-attn) | MIT（见配套仓库） |
| `small_t_i8_volta_v2.cuh` 解码内核 | [huangserva/ninfer-v100-tpx](https://github.com/huangserva/ninfer-v100-tpx) | Apache-2.0 |
| 六个 sm70 提交 | [Flo5k5/ninfer-v100-sm70](https://github.com/Flo5k5/ninfer-v100-sm70) | **再分发前请自行核实** |

**本仓库不含任何内核源码。** 它只是一份记录：做了什么、量到了什么、什么没用。
代码请从上面这些上游仓库获取，并自行核对各自许可。

## 本文数字是怎么核的

本文每一个数字都能追到 `logs/` 里的某一行，`claims.md` 把每条断言映射到它的来源行。
「完整性」一节可用以下命令复现：

```sh
L=ninfer-serve.log
grep -ac 'req#[0-9]* started'          "$L"   # 53
grep -ac ' done | '                    "$L"   # 53
grep -ac 'rejected during'             "$L"   # 0
grep -ac 'failed during'               "$L"   # 0
grep -ac 'queue timeout'               "$L"   # 0
grep -ac 'context length exceeded'     "$L"   # 0
grep -aE 'max output 8,192'            "$L"   # 3 条摘要调用
```

运维日志格式本身不含 prompt、生成文本、请求体或凭据 —— 所以原始日志可以不脱敏直接公开。

## 复现

1. 为 sm_70 构建 NInfer（见上游仓库；需要 CUDA 12.x —— **CUDA 13 已经不支持 Volta**）。
2. 打上两处内核移植（预填见配套仓库；解码见上面 tpx 与 Flo5k5 两个仓库）。
3. 用本文顶部的命令行启动引擎，并用 `NINFER_SM70_ATTN_V2=1` 启用 v2 内核。
   先把 `.wslconfig` 抬到 `memory=32GB` —— 14 GiB 页锁定 host KV 加上其余部分，16 GB 装不下。
4. 用任何 OpenAI 兼容客户端驱动它，**保持单流**。与 `logs/done-lines-raw.txt` 对照。
