# claims.md —— 每条断言的来源

本文件把 README 里的每一个数字映射到它的原始来源。**核对方式：对每一行，用「核对命令」重跑一遍，与「期望」比对。对不上就是有问题。**

---

## A. 运行完整性

来源：`logs/ninfer-serve.log.snapshot-final`

| 断言 | 核对命令 | 期望 |
|---|---|---|
| 请求总数 | `grep -ac 'req#[0-9]* started' logs/ninfer-serve.log.snapshot-final` | `53` |
| 完成数 | `grep -ac ' done \| ' logs/ninfer-serve.log.snapshot-final` | `53` |
| 准备阶段被拒（400） | `grep -ac 'rejected during' logs/ninfer-serve.log.snapshot-final` | `0` |
| 生成阶段失败 | `grep -ac 'failed during' logs/ninfer-serve.log.snapshot-final` | `0` |
| 排队超时（503） | `grep -ac 'queue timeout' logs/ninfer-serve.log.snapshot-final` | `0` |
| 上下文超限（400） | `grep -ac 'context length exceeded' logs/ninfer-serve.log.snapshot-final` | `0` |
| OOM / CUDA 错 | `grep -aicE 'out of memory\|cudaError\|CUDA error' logs/ninfer-serve.log.snapshot-final` | `0` |
| 摘要调用条数 | `grep -ac 'max output 8,192' logs/ninfer-serve.log.snapshot-final` | `3` |

## B. 阶梯表

来源：`logs/done-lines-raw.txt`（与 A 的快照同源，逐行原文）。
README 阶梯表的每一行 = 该文件里对应 `req#N done` 那一行的直接转写 —— **但「复用来源」那一列除外**：
日志在**命中时**会打印 `private endpoint` / `turn closure` / `shared prefix` 等路径标签，
**未命中时不打印任何标签，只有 `cache 0 (0.0%)`**。表里的 `root` 是**按"未命中"加注的**
（`root` 是引擎文档里该路径的正式名字），`root（探针）`里的"探针"依据来自被测会话自己的台账
（`logs/under-test-ledger.md`），**不是引擎日志**。除这一列外，22 行 × 6 个数值列共 132 个值
逐字命中，0 处不符（2026-09-29 由独立核对者复算确认）。

| req | 该行关键字段（原文值） |
|---:|---|
| 3 | prompt 40,119 · cache 0 (0.0%) · TTFT 43.1s · prefill 1.00k · decode 55.5 · mtp 260/531 (49.0%) |
| 7 | prompt 49,540 · cache 49,412 (99.7%, private endpoint) · TTFT 711 ms · prefill 203.0 · decode 59.2 · 91/162 (56.2%) |
| 9 | prompt 48,880 · cache 43,625 (89.2%, turn closure) · TTFT 7.3s · prefill 728.6 · decode 51.6 · 2,175/5,064 (43.0%) |
| 14 | prompt 65,536 · cache 65,509 (100.0%, private endpoint) · TTFT 1.9s · prefill 14.2 · decode 56.0 · 415/822 (50.5%) |
| 24 | prompt 88,096 · cache 85,323 (96.9%, private endpoint) · TTFT 4.7s · prefill 602.2 · decode 47.2 · 1,581/3,697 (42.8%) |
| 32 | prompt 98,612 · cache 98,559 (99.9%, private endpoint) · TTFT 4.5s · prefill 11.9 · decode 89.4 · 147/177 (83.1%) |
| 33 | prompt 88,528 · cache 0 (0.0%) · TTFT 1m 46.8s · prefill 829.8 · decode 72.4 · 17/18 (94.4%) |
| 37 | prompt 134,156 · cache 0 (0.0%) · TTFT 3m 57.6s · prefill 565.0 · decode 53.2 · 332/559 (59.4%) |
| 38 | prompt 167,428 · cache 134,655 (80.4%, private endpoint) · TTFT 1m 11.2s · prefill 460.9 · decode 55.8 · 321/468 (68.6%) |
| 39 | prompt 201,700 · cache 167,876 (83.2%, private endpoint) · TTFT 1m 23.7s · prefill 404.8 · decode 49.2 · 1,469/2,331 (63.0%) |
| 40 | prompt 81,919 · cache 48,875 (59.7%, turn closure) · TTFT 51.0s · prefill 648.7 · decode 67.4 · 2,961/4,283 (69.1%) |
| 41 | prompt 136,497 · cache 0 (0.0%) · TTFT 3m 20.2s · prefill 688.3 · decode 44.9 · 242/529 (45.7%) |
| 43 | prompt 175,017 · cache 0 (0.0%) · TTFT 4m 44.2s · prefill 616.1 · decode 46.4 · 3,703/6,767 (54.7%) |
| 44 | prompt 206,364 · cache 138,594 (67.2%, turn closure) · TTFT 2m 40.8s · prefill 422.5 · decode 42.3 · 1,350/2,631 (51.3%) |
| 45 | prompt 88,228 · cache 0 (0.0%) · TTFT 1m 51.2s · prefill 799.6 · decode 66.3 · 1,965/2,873 (68.4%) |
| 47 | prompt 183,938 · cache 135,761 (73.8%, turn closure) · TTFT 1m 49.2s · prefill 444.0 · decode 46.6 · 10,137/17,778 (57.0%) |
| 48 | prompt 136,960 · cache 0 (0.0%) · TTFT 3m 20.1s · prefill 689.8 · decode 58.5 · 3,154/4,689 (67.3%) |
| 49 | prompt 113,562 · cache 0 (0.0%) · TTFT 2m 30.9s · prefill 756.0 · decode 58.4 · 100/151 (66.2%) |
| 50 | prompt 114,286 · cache 113,557 (99.4%, turn closure) · TTFT 1.8s · prefill 429.8 · decode 57.9 · 19,308/30,553 (63.2%) |
| 51 | prompt 146,219 · cache 114,281 (78.2%, turn closure) · TTFT 1m 4.1s · prefill 501.5 · decode 52.5 · 17,138/27,395 (62.6%) |
| 52 | prompt 172,414 · cache 172,065 (99.8%, private endpoint) · TTFT 1.6s · prefill 280.4 · decode 50.6 · 2,078/3,344 (62.1%) |
| 53 | prompt 175,632 · cache 175,579 (100.0%, private endpoint) · TTFT 7.7s · prefill 7.0 · decode 52.1 · 449/689 (65.2%) |

**README 的直接派生断言，全部可从 B 重算：**

| 断言 | 推导 | 期望 |
|---|---|---|
| 缓存命中行 TTFT 区间 | B 中 cache ≥99% 的行取 min/max | `0.54 s`（req#29）/ `7.7 s`（req#53） |
| 未命中行 TTFT 区间 | B 中 cache 0.0% 且 prompt ≥40k 的行 | `43.1 s`（req#3）/ `4 m 44.2 s`（req#43） |
| 真实深度下 0% 的行数 | B 中 cache 0.0% 且 prompt ≥40k 的行计数 | `9`（req#3/33/37/41/43/45/46/48/49） |
| 解码最小值 / 最大值 | B 中 prompt ≥40k 的 decode 列 | min `42.3` / max `89.4` |
| ≤167k 区间解码 | B 中 prompt ≤167,428 且 ≥40k 的 **42 行**（排除 #40/#45/#48） | `44.9 – 89.4` |
| ≤167k 区间接受率 | 同上 42 行 | `42.8 – 94.4%`（min = #24） |
| ≤167k 区间预填 | 同上 42 行 | `10.5 – 1000`（**极值无解释力**：浅层小增量行会算出极端值） |
| 175–206k 区间解码 | B 中该带共 **5 行**：#39 201,700 / #43 175,017 / #44 206,364 / #47 183,938 / #53 175,632 | `42.3 – 52.1` |
| 压缩后区间解码 | B 中 **#41 / #46 / #49 / #50** 四行 | `44.9 – 58.4` |

⚠️ **口径提醒（2026-09-29 订正）**：README 早期版本写「≤167k 解码 53–58」，**那个说法已删除** ——
它把「99k→167k 五行」当成了整区间，真实逐行值是 `44.9 – 89.4`（42 行里 24 行在 [53,58] 之外）。
**任何区间数字都以 B 的逐行原值为准，且请自己重算。**

## C. 压缩循环

来源：`logs/req-events-raw.txt`（`started` 行）+ `logs/done-lines-raw.txt`（`done` 行）

| 断言 | 来源 |
|---|---|
| 3 轮压缩 | `grep -aE 'max output 8,192' logs/ninfer-serve.log.snapshot-final` → 3 行，时间 08:01:06.688 / 08:18:07.180 / 08:31:40.538 |
| 每轮触发时的会话 prompt | 各自前一条 `done` 行：req#39 = 201,700；req#44 = 206,364；req#47 = 183,938 |
| 摘要调用 prompt / 输出 / 总耗时 | req#40 = 81,919 / 4,209 / 1m 53.6s；req#45 = 88,228 / 2,773 / 2m 33.1s；req#48 = 136,960 / 4,491 / 4m 37.1s |
| 压缩后第一条请求 cache 0% | req#41 / req#46 / req#49 三行的 `cache 0 (0.0%)` |
| 恢复 | req#42 = 98.5%；req#50 = 99.4% |
| 逐轮合计（**不是平均 5 分钟**） | 第 1 轮 `1m53.6s + 3m20.2s = 5m13.8s`；第 2 轮 `2m33.1s + 3m24.0s = 5m57.1s`；第 3 轮 `4m37.1s + 2m30.9s = 7m8.0s` |

⚠️ 「摘要调用是压缩」这一判定依据是 `max output 8,192` 这个特征值 —— 它是客户端摘要输出上限的默认值，
**不是直接证据**。旁证：这三条都是 `stop token` 结束、输出 2,773–4,491 的长文本、且紧跟在一条越过
80% 阈值的请求之后。**若你的客户端把 max output 8,192 用在别处，这个判定不成立。**

## D. 环境与启动

来源：`logs/environment-raw.txt`、`logs/startup-raw.txt`

| 断言 | 来源行 |
|---|---|
| V100-SXM2-32GB，31,522 / 32,768 MiB，33 °C | `environment-raw.txt` 的 nvidia-smi CSV 第 4 行 |
| 3080 Ti 约 800 MiB | 同文件第 3 行 |
| 引擎完整命令行 | 同文件 `### engine cmdline ###` 段 |
| md5 `6b104a4464cdab6687351c00770d7ba8`、299,287,880 字节 | 同文件 `### binary identity ###` 段 |
| WSL 32,096 MiB / swap 8,192 | 同文件 `### WSL ###` 段 |
| `.wslconfig memory=32GB` / `swap=8GB` / `networkingMode=nat` | 同文件末段 |
| `NINFER_SM70_ATTN_V2=1` | 同文件 `### engine pid + NINFER env ###` 段 |
| weights 20.0 GiB | `startup-raw.txt` 第 2 行 |
| host state 1.72 GiB / host KV 14.0 GiB | `startup-raw.txt` 第 4、6 行 |
| KV 245,056 tokens / pages 3,829/3,829 / runtime 10.5 GiB / free 188.3 MiB | `startup-raw.txt` 第 10 行 |
| context cache host 12 states / 14.0 GiB KV / private 4 / shared 8 / anchors 8 | `startup-raw.txt` 第 11 行 |

**KV 每 token 成本**：`10.5 GiB ÷ 245,056 = 46,007 B/token`（由上面最后两行直接算出；早先写 46,005）。
README 里写「约 45 KiB/token」，因为 `runtime 10.5 GiB` 是四舍五入值。

## E. 内核 A/B 数字

来源：`evidence/v2ab/*.json`，取每臂 `results[]` 里 `label == "long-cold"` 的那条

| 断言 | 文件 | 字段 | 期望值 |
|---|---|---|---|
| 原版 + mtp | `v2ab-v2off-200k.json` | `results[1].decode_tok_s` | `32.56532942325025` |
| v2 + mtp | `v2ab-flo-v2-200k.json` | `results[1].decode_tok_s` | `59.19603086183815` |
| 原版 + none | `v2ab-v2off-nospec-200k.json` | `results[1].decode_tok_s` | `15.20774511610815` |
| v2 + none | `v2ab-flo-nospec-v2-200k.json` | `results[1].decode_tok_s` | `21.842699455932266` |
| +43.6% | 上面两行的比值 | `21.842699455932266 / 15.20774511610815 - 1` | `0.436287844…` |

⚠️ **本节 2026-09-29 订正。** 早先这里写了一句「用四舍五入后的 `21.8427 / 15.2077 - 1` 会得到
`0.4359`」—— **那句话本身是错的**：实际算出来是 `0.436292`。**+43.6% 的结论一直是对的**，
错的是那条画蛇添足的警告，已删除。**核对时用全精度表达式即可。**
| prompt 170,607 | 任一同上文件 | `results[1].prompt_n` | `170607` |
| `--greedy` | 任一同上文件 | `extra` | `--greedy` |
| 接受率（v2 + mtp） | `v2ab-flo-v2-200k.json` | `results[1].accept_rate` | `0.7431` |
| 接受率（原版 + mtp） | `v2ab-v2off-200k.json` | `results[1].accept_rate` | `0.5209` |
| 内核单次 1.637 → 0.689 ms，n=101/臂 | **不在本仓库的原始数据里** | — | ⚠️ 见下 |

⚠️ **内核单次调用耗时（1.637 / 0.689 ms）来自本机另一份 trace 分析报告，不在本仓库证据内。
标为 `[未随证据发布]`。** 若需要，请当作二手数字看待。

## F. 「试过但没用的东西」的来源

这一节的结论**不在本仓库的原始日志里**，来自本机 2026-09-28 的引擎台账（未发布）。
逐条标注：

| 断言 | 证据强度 |
|---|---|
| `--kv-dtype fp8` ⇒ 预填 −88%、解码 −88%、TTFT 12.7s → 1m50s | 台账记录的实测（未随本仓库发布） |
| `nvfp4`/`k8v4` ⇒ Volta 拒收，32 ms 内 FATAL | 台账记录的实测原文（未随本仓库发布） |
| `--prefill-chunk 8192` ⇒ 预填 −41% | 台账记录的实测（未随本仓库发布） |
| `--media-*-mib` 是上限不是预分配 | 台账记录的实测（未随本仓库发布） |
| 子代理并发 ⇒ 503 排队超时 | **本仓库日志内有旁证**：`03:55` 前后两条 `failed during generation \| HTTP 503 \| request queue timeout`（在另一份快照里，不在本次 final 快照内）—— ⚠️ 见下 |
| `exec VAR=1 cmd` 无效 | 上游 bash 语义，非本机实测 |
| 两个启动器只有一个是活的 | 本机两次事故记录（未随本仓库发布） |

⚠️ 本仓库的 final 日志快照是 **07:31 那次成功启动之后**的，所以更早那次 503 事故**不在其中**。

## G. 两次失败启动的 FATAL 行 —— 来源不同于日志

| 断言 | 原文 | 来源 |
|---|---|---|
| 262144 拒启 | `FATAL server failed during startup \| requested Engine runtime reservation requires 12004767744 bytes, but only 11330617856 bytes are available for runtime capacity`（2026-09-29 07:13:12） | **启动器控制台输出**，非引擎日志 |
| 20 GiB host KV 拒启 | `FATAL server failed during startup \| cudaMallocHost failed: cudaErrorMemoryAllocation: out of memory`（2026-09-29 07:19:21） | 同上 |

**这两次尝试的引擎日志已被 07:31 那次成功启动覆盖，本仓库无法复现它们。**
原始文本另存于 `evidence/failed-startup-console.txt`。
⇒ README 里「约 247,428 token 是硬顶」这个数字由第一条 FATAL 行算出
（`12,004,767,744 ÷ 262,144 = 45,794.55 B/token`，`11,330,617,856 ÷ 45,794.55 ≈ 247,425.8`，文档写 ≈247,428 是整数近似），
**属于二手证据**。

## H. pinned 内存的 CUDA 探针 —— 未随本仓库发布

「单次 `cudaMallocHost` 上限 15 GiB / 累计 28 GiB / 与 WSL 内存无关」来自本机自写的 CUDA 探针
（源码 `_pinned_probe.cu` / `_pinned_probe2.cu`），**不在本仓库证据内**。
探针源码片段另存于 `evidence/pinned-probe-notes.txt`（说明与方法，非完整可编译副本）。
**标为 `[未随证据发布]`。**

---

## 结论：**不是「其余全部数字都能复现」** —— 2026-09-29 订正

早先这里写「其余全部数字都能在 `logs/` 里逐行复现」，**被独立核对推翻**。正确的划分是：

**能逐行复现的**：逐行主表（22 行 × 6 数值列）、7 个完整性计数、压缩循环明细（9 个 prompt 值 +
3 条摘要的 output 与总耗时 + 3 条 0% + 2 个恢复值）、A/B 四值 + 两个接受率 + `prompt_n` + `--greedy`、
环境与启动 13 项。

**追不到 `logs/` 的（四类，README 正文已逐条标 `[未随证据发布]`）**：

1. **内核单次耗时 1.637 / 0.689 ms（n=101）** —— 来自未发布的 trace 分析；
2. **两次失败启动的 FATAL 行** —— 来自启动器控制台，对应引擎日志已被 07:31 那次成功启动覆盖；
3. **页锁定内存探针 15 GiB / 28 GiB** —— 只有方法与结论说明（`evidence/pinned-probe-notes.txt`），
   连探针输出那张表也是**转述**；
4. **「试过但没用的东西」整节** —— 来自未发布的引擎台账（F 节已逐条标注）。

另有若干**单点或间接**证据：`峰值 31,522 MiB` 实为**一个采样点**；`WSL2 Ubuntu-24.04` 的机器输出
未随仓库发布（该名称来自启动器的 `$Distro` 与 `.wslconfig`）；`state image 只有 10 个` 与硬顶
`247,428` 分别来自**引擎源码**与**手抄控制台行**，都不是日志证据。

**§2 与 F 节里那句「本仓库日志内有旁证：03:55 两条 HTTP 503…（在另一份快照里，不在本次 final
快照内）」自相矛盾**（既说"本仓库内有"又说"不在本次快照内"），且核对者实测 final 快照里
`503` 出现 **0** 次、`FATAL` 出现 **0** 次 —— **以实测为准，那条旁证不成立。**

⚠️ **归纳层要特别小心。** 本次核对找出的 19 处对不上，**全部集中在归纳/派生表述**（区间归并、
总括句、单位、平均值），原始行本身 0 处编造。凡涉及区间的数，请回到逐行原值自己重算。
