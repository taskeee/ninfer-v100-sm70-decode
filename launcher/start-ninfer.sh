#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Start NInfer with the configuration measured on this project's V100.
#
# Every flag here is explained in ../README.md. The three that are NOT the
# upstream defaults, and the reason each one exists:
#
#   --host-state-slots 12      logical_state_capacity = (max_concurrency +
#                              device_state_slots) + host_state_slots must be
#                              >= max_private_continuations +
#                              max_shared_prefixes + 1, or some addressable
#                              checkpoints cannot be materialised.
#   --host-kv-mib 14336        byte pool for reusable prefixes. ~45 KiB/token,
#                              and a SINGLE cudaMallocHost caps at ~15 GiB on
#                              this box (it does NOT scale with WSL memory).
#   --pending-timeout-ms 900000  at the 30 s default, any second request is
#                              killed with HTTP 503 instead of waiting.
#
# NOTE the environment assignment is exported BEFORE exec. `exec VAR=1 cmd`
# does not work: bash parses the assignment as the program name.
# ---------------------------------------------------------------------------
set -euo pipefail

# --- edit these three ------------------------------------------------------
ENGINE="${ENGINE:-/home/ai/ninfer-v100/build-v100/apps/ninfer-serve}"
MODEL="${MODEL:-/home/ai/models/qwen3_8_27b_nvfp4.ninfer}"
PORT="${PORT:-8110}"
# ---------------------------------------------------------------------------

MODEL_ID="${MODEL_ID:-qwen3.8-27b-uncen}"
DEVICE="${DEVICE:-1}"

if [ ! -x "$ENGINE" ]; then echo "engine not executable: $ENGINE" >&2; exit 1; fi
if [ ! -f "$MODEL"  ]; then echo "model not found: $MODEL" >&2; exit 1; fi

# Arms the ported tpx v2 int8 decode kernel. Must be in the environment of the
# engine process, not on the command line.
export NINFER_SM70_ATTN_V2=1

echo "starting NInfer on device $DEVICE, port $PORT"
echo "  engine : $ENGINE"
echo "  model  : $MODEL"
echo "  (first start loads ~20 GiB of weights; expect ~1.5 min plus the pinned-host allocation)"

exec stdbuf -oL -eL "$ENGINE" "$MODEL" \
  --host 127.0.0.1 --port "$PORT" --model-id "$MODEL_ID" \
  --max-context 245000 --kv-capacity 245000 --prefill-chunk 2048 \
  --max-concurrency 1 --kv-dtype int8 \
  --device-state-slots 1 --host-state-slots 12 --host-kv-mib 14336 \
  --pending-timeout-ms 900000 \
  --max-private-continuations 4 --max-shared-prefixes 8 \
  --max-long-anchors-per-continuation 8 \
  --spec mtp --draft-tokens 3 --lm-head-draft \
  --vision --device "$DEVICE"
