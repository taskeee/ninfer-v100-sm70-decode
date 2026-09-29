# Qwen3.8-27B 载体满载测试（2026-09-29）

## 任务
模拟正常使用，把本会话上下文拉满、触发自动压缩、打满循环，验证载体（DSH + NInfer + Qwen3.8-27B nvfp4）参数有没有问题；顺带采集不同上下文深度下 agent 实际输出速度。不开子进程。

## 被测参数（实测核对过）
- 引擎：WSL Ubuntu-24.04，NInfer `build-v100/apps/ninfer-serve`，device 1 = Tesla V100 32GB（3080Ti 空闲）
- 模型：`/home/ai/models/qwen3_8_27b_nvfp4.ninfer`，model-id `qwen3.8-27b-uncen`，端口 8110
- 关键参数：`--max-context 245000 --kv-capacity 245000 --kv-dtype int8 --device-state-slots 1 --host-state-slots 12 --host-kv-mib 14336 --spec mtp --draft-tokens 3 --lm-head-draft --prefill-chunk 2048 --max-concurrency 1 --pending-timeout-ms 900000`，env `NINFER_SM70_ATTN_V2=1`
- DSH：settings.yaml 模型窗口 245000；agent 预设 `standard-noprune`（pruner thresholdChars=1000000≈不裁）；压缩=主模型 27B 自己摘要（无独立 summarizationProvider）
- 压缩触发：`dsh-compaction-basic` 默认 thresholdRatio 0.8 → **196,000 token** 到点，保留尾 16%（39,200 token）；step 边界自动触发
- 速度数据源：WSL `/home/ai/ninfer-serve.log` 的 `req#N done` 行（prompt 深度/TTFT/prefill tok/s/decode tok/s/MTP 接受率/cache 命中率）

## 成功标准（验收）
1. 本会话上下文自然增长到 ≥196k，自动压缩真实发生（引擎日志出现长 prefill + 长输出的摘要请求；会话转录出现 compaction 事件）
2. 压缩后连续性：重读 task.md 与 checksum 抽查通过，测试参数/进度计数无断档，不重做已完成部分
3. 速度表：至少覆盖 3 个深度档（低/中/高），decode tok/s 与 MTP 接受率无异常掉速，无 OOM/报错
4. 第二循环：压缩后再填充一次，再触发一次压缩（打满循环）
5. 全程 V100 显存 < 32GB、无引擎崩溃、无 DSH 报错

## 禁令
- 不开子进程/子代理（显卡并发会把主窗口顶掉）
- 不重启 NInfer、不重启 dsh web
- 不动任何参数（纯测量；发现问题只记录）
- 填充用 filler.txt 逐块 read（每块 800 行≈20k token），不整文件一次读
- 每次压缩前后：引擎日志 `req#` 计数必须对上（无丢失请求）

## 方法
- 填充：`filler.txt` 共 8000 行，每行 `L<5位行号> <word> <checksum>`，checksum = i*7 % 9973。每读完一块，用引擎日志最近 `req#` 行记录该深度实测速度
- 压缩验证：压缩后读 `filler.txt` 指定行（read 带 offset/limit），核对行号与 checksum 一致
- 控制深度 probe：`probe.py <目标token> <max_out>`，直连 8110 流式请求，报 TTFT/decode 速度（补充 210k+ 档位）

## 已完成
- 环境：task.md / filler.txt（16000 行 745KB≈550k token，800 行/块≈27k token）/ probe.py
- baseline probe：目标 30k 实测 prompt 88,528 token（校准系数 1.35 已修正）；TTFT 107s（冷 prefill ≈828 tok/s）
- 填充 chunk 1-3（filler.txt 行 1-2400 已读入本会话）；checksum 抽查 3 处全对：L00799=5593、L01426=9、L02239=5700
- 速度表（本会话真实 agent 请求，引擎日志 req#）：
  | req# | prompt | decode | MTP接受率 | cache | TTFT |
  |---|---|---|---|---|---|
  | 34 | 98,876 | 53.8 tok/s | 54.1% | 99.9% | 678ms |
  | 35 | 100,540 | 57.1 tok/s | 61.0% | 99.7% | 909ms |
  | 36 | 101,162 | 57.3 tok/s | 59.1% | 99.5% | 1.2s |
  | 37 | 134,156 | 53.2 tok/s | 59.4% | 0.0% | 3m57.6s |
  | 38 | 167,428 | 55.8 tok/s | 68.6% | 80.4% | 1m11.2s |
- ⚠ 发现：探针请求（88.5k，07:5x）把本会话前缀挤出缓存 → req#37 cache 0%、TTFT 3m57s；req#38 恢复 80.4%（复用了 req#37 前缀）。decode 速度 99k→167k 全程 53~57 tok/s 无衰减；MTP 接受率随深度上升（54%→69%）
- **压缩#1 已发生**（08:01-08:03，引擎日志证据链）：req#39 201,700（104 msgs，越过 196k 阈值）→ req#40 摘要请求 81,919 prompt→4,209 输出（1m54s，decode 67.4 tok/s、MTP 69.1% 全场最快，max output 8,192=maxTokens 默认）→ req#41 136,497（38 msgs，cache 0%、TTFT 3m20s，官方设计：checkpoint 从首个被替换 token 起作废前缀）；req#42 恢复 cache 98.5%。净省 ~65k≈32%
- 压缩机制（官方文档核对：本机装包 README + 官方 subsystem 页）：① 每次触发只压"最老平衡段"换一条摘要，尾巴原样保留，非全量压到 16%；② system prompt/tools/session prefix 永不压缩（本会话 47 工具 schema = 永久底座）；③ 官方已知限制：meter 4 字符/token 启发式低估密排 ASCII（实测 1.35）→ 尾巴实际约 3 倍于预算，压缩提前停（136k 底 vs 39k 预算）；④ compactionRetries=1；旧 checkpoint 再压缩时合并非照抄
- 连续性验证#1 通过：台账重读无断档；checksum L02400=6827、L02850=4、L04618=2407 全对（i*7%9973）；未重做已完成部分
- **压缩#2、#3 已发生（08:18–08:36，打满循环超额完成）**：req#44 206,364（49 msgs，越过 196k）→ req#45 摘要 88,228→2,773（decode 66.3、MTP 68.4%、TTFT 1m51s）→ req#46 138,406（24 msgs）；req#47 183,938（29 msgs，provider 未过 196k，但 meter 把长推理输出+新尾巴按字符启发式计入、估 >196k → 照样触发，官方 meter 机制实锤）→ req#48 摘要 136,960→4,491（decode 58.5、MTP 67.3%、TTFT 3m20s）→ req#49 113,562（12 msgs）→ req#50 114,286 cache 99.4%。req# 39→50 链条连续无丢失（禁令⑤验收通过）
- 速度表补全（req#43–50，真实 agent 请求）：175,017/46.4 t/s/54.7%/cache 0%/TTFT 4m44s；206,364/42.3/51.3%/67.2%/2m41s；138,406/57.3/63.2%/0%/3m24s；183,938/46.6/57.0%/73.8%/1m49s；113,562/58.4/66.2%/0%/2m31s；114,286/57.9/63.2%/99.4%/1.8s
- ⚠ **深度掉速发现**：175–206k 档 decode 42–47 tok/s（≤167k 为 53–58）、prefill 422–444 tok/s（其余 616–799）、MTP 接受 51–57%（其余 63–69%）三重齐降；压缩回 114–138k 后恢复到 57–58 tok/s/63–66%。与 KV 压力吻合（kv-capacity 245k int8 + 32GB 设备 + host 卸载 14GB，机制为估算）；无 OOM 无崩溃，优雅降级
- 连续性验证#2/#3 通过：task.md 重读无断档（req#45 压缩后重读成功）；checksum L04000=8054、L04800=3681、L05599=9274 全对；未重做已完成 chunk（filler 只从 4001 单向推进）
- checkpoint 合并观察：新 checkpoint（req#48 产物）大体保留旧 checkpoint 文字，27B 摘要器把过期行「fetches not yet done」也带了进去（合并指令要求去旧，27B 服从度一般）；关键事实无丢失

## 在做
- 打满循环完成（压缩 #1/#2/#3 全部真实发生）；余 = 最终显存核对 + 最终报告落盘

## 没做完和踩的坑
- probe.py 初版 chars_per_tok=3.8 错了（结构化文本实测 1.35），目标 30k 打出 88.5k
- 探针与本会话共享引擎前缀缓存，探针一跑本会话下轮 cache 归零（TTFT 代价 4 分钟）；后续探针要么放压缩前最后一轮、要么接受一次重 prefill

## 死路
- （空）

## 最终报告（结论，2026-09-29 08:4x 收口）

### 成功标准验收
| # | 标准 | 结果 |
|---|---|---|
| 1 | 上下文 ≥196k + 自动压缩真实发生 | ✓ 三次：req#40（201,700→136,497）、req#45（206,364→138,406）、req#48（183,938+尾巴经 meter 估算过线→113,562）。引擎日志 3 条摘要请求（max output 8,192），会话转录 3 次 checkpoint |
| 2 | 压缩后连续性 | ✓ 两轮重验：task.md 重读无断档、checksum 抽查全对（6 处）、无 chunk 重做 |
| 3 | 速度表 ≥3 深度档、无异常掉速/无 OOM | ✓ 六档（99–101k / 134k / 167k / 175–206k / 114–138k 压后 / 摘要 82–137k）；175–206k 有降级但属 KV 压力可解释、压缩后恢复，无 OOM 无报错 |
| 4 | 第二循环 | ✓ 超额：压缩#1 之后又跑满两循环（#2、#3） |
| 5 | 显存 <32GB、无崩溃 | ✓ V100 峰值 31,522/32,768 MiB（96.2%）、39°C；3080Ti 全程 842 MiB 空闲；无引擎崩溃、无 DSH 报错 |

### 速度结论（真实 agent 请求，非探针）
- ≤167k 上下文：decode 53–58 tok/s 全程平稳、MTP 59–69% → 无深度衰减
- 175–206k 上下文：decode 42–47、prefill 422–444、MTP 51–57% 三重齐降（KV 压力，机制为估算：int8 KV 245k + 32GB 设备 + host 卸载 14GB）；压缩回 114–138k 后恢复 57–58 tok/s / 63–66%
- 摘要请求档（medium thinking、8,192 cap）：58–67 tok/s、MTP 67–69%，全会话最快
- TTFT：cache 命中 1.8–4s；压缩后/前缀被挤出需 2.5–5min 全量 prefill（设计使然，官方文档「checkpoint 从首个被替换 token 起作废前缀」）

### 压缩机制结论（官方文档 + 实测双重核对）
- 用户观察「只压缩 20–32%」= 设计行为：① 每次触发只把最老平衡段换成一条摘要，非全量压到 16%；② system prompt + 47 工具 schema + 会话前缀 = 永久底座不压缩；③ meter 4 字符/token 启发式低估密排 ASCII（实测 1.35）→ 保留尾实际 ≈3 倍于 39.2k 预算，压缩提前停
- meter 触发实锤：压缩#3 时 provider 只报 183,938（<196k 阈值），但 meter 把长推理输出+新尾巴按字符计数估过线照样触发
- checkpoint 合并：27B 摘要器大体保留旧 checkpoint 文字，过期 pending 行会残留（合并指令服从度一般），关键事实无丢失

### 参数判定
- **无需改参数**。现配置满载稳定：245k 窗口、int8 KV、host 卸载 14GB、MTP draft 3、concurrency 1、DSH 压缩 0.8/0.16/8192 全部按预期工作
- 已知边界（非故障）：175–206k 单段深度档预期 decode ~42–47 tok/s；自动压缩在溢出前接住，实测全程无 OOM
