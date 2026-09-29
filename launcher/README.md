# launcher/

A runnable version of the command line documented in [`../README.md`](../README.md), so you do not
have to transcribe flags.

| File | What it is |
|---|---|
| `start-ninfer.sh` | Bash starter for **inside WSL**. Three variables at the top (`ENGINE`, `MODEL`, `PORT`); everything else is already correct. `exec`s the engine, so its log goes to whatever you redirect it to. |
| `wslconfig.example` | The `.wslconfig` this configuration needs, with the reason each value is what it is. |

## What is intentionally NOT here

- **No Windows wrapper.** The launcher this project actually uses is a PowerShell script with
  machine-specific logic: it frees the V100, stops a competing llama console, waits for the endpoint
  to answer, runs a self-check, and switches between two engine binaries. **None of that is portable**,
  and shipping a half-working copy would be worse than shipping nothing. Start `start-ninfer.sh` from
  WSL, or write your own wrapper around it.
- **No kernel source.** The two kernel ports come from the upstream repositories named in the
  [README](../README.md#attribution-and-licences); check each licence yourself.
- **No model artifact.** `MODEL` points at a `.ninfer` container you obtain yourself.

## Order of operations

1. Build NInfer for **sm_70** (CUDA **12.x** — CUDA 13 dropped Volta).
2. Apply the kernel ports (see the README's attribution table).
3. Put `wslconfig.example` at `C:\Users\<you>\.wslconfig`, then `wsl --shutdown`.
4. From WSL: `MODEL=/path/to/model.ninfer ENGINE=/path/to/ninfer-serve ./start-ninfer.sh`
5. Watch the first lines of its output. What you should see, verbatim, is:

```
weights ready | 20.0 GiB | ...
pinning host state | 1.72 GiB
pinning host KV    | 14.0 GiB
engine ready | qwen3.8-27b/nvfp4 | ...
capacity | KV 245,056 tokens, int8, explicit | pages 3,829/3,829 | runtime 10.5 GiB | free 188.3 MiB
context cache | 1 active + 1 cached device states | host 12 states, 14.0 GiB KV | private 4 | shared 8 | anchors 8
```

**If `pinning host KV` is not 14.0 GiB, or the process dies there with
`cudaMallocHost failed: cudaErrorMemoryAllocation`,** drop `--host-kv-mib` — see the README's
pinned-memory note. The ceiling is a single-allocation limit, not free-RAM.

## What to expect once it runs

Numbers, conditions, and the honesty caveats are in the [README](../README.md). The two the README
repeats because they are the ones people get wrong:

- **Decode must be read together with MTP acceptance.** 42–89 tok/s is the honest range across the
  measured session; a single decode figure without its acceptance rate means nothing here.
- **After any client-side context compaction, the next request re-prefills from scratch**
  (measured 5–7 minutes per cycle). That is by design, and more memory does not fix it.
