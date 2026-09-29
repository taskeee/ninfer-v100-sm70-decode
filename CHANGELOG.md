# Changelog

Everything here is a record of what changed **in this repository** (documents and data), not in the engine.
The engine and kernel changes are described in the README and live in the upstream repositories.

## 2026-09-29 — first public snapshot, then two rounds of correction

**Published**

- 53-request measured session under a real agent load (Qwen3.8-27B, one Tesla V100-SXM2-32GB, single stream),
  with the raw engine log behind every number.
- `logs/` — unedited copies: the 53 `done` lines, the `started` lines, startup and environment capture,
  the full engine-log snapshot, the session's own ledger, the upstream identity check.
- `evidence/` — the four raw A/B arms (10 JSON files), the two failed-startup console captures,
  the pinned-memory probe notes.
- `launcher/` — a runnable `start-ninfer.sh` plus the `.wslconfig` this configuration needs.
- `claims.md` — every claim mapped to the line that supports it, **including the claims that cannot be traced**.

**Corrected** (found by independent processes that took no part in producing the document; see `claims.md` §I for the full history)

- The depth table was rewritten from per-row values: an earlier version generalised 5 rows into a whole band and
  missed rows in two other bands.
- "Every number traces to `logs/`" was false — four kinds of numbers do not, and each is now marked inline.
- The ~9.7 GiB pinned-memory figure was a leftover from an older configuration (it is 15.72 GiB).
- **A false claim that the 175k–206k acceptance rates were all below the ~167k median was deleted**
  (3 of those 5 rows are above the median, 56.15%).
- The hard-ceiling arithmetic was unified: `12,004,767,744 ÷ 262,144 = 45,794.5547 B/token` ⇒
  `11,330,617,856 ÷ 45,794.5547 ≈ 247,423 tokens`. An earlier version mixed an integer denominator with a rounded
  one and stated `≈247,428`, a value **no denominator can produce**; the explanation invented for it was removed.
  (For the record: an intermediate "fix" of ours changed the correct `45,794.55` to a wrong `45,794.58` —
  caught by an independent verifier, then corrected.)

**Added**

- `LICENSE` — Apache-2.0, matching the companion repository.
- `data/session-53-requests.csv` + `data/README.md` — the whole session machine-readable, so nobody has to parse logs.
- English block at the top of `README.md`, plus `README.en.md`; repository topics filled in (20).
- This changelog.

**Restructured**

- `README.md` / `README.en.md` were reordered to read as a guide rather than an audit trail:
  what problem this solves → what it achieves → how to run it → the four settings → pitfalls → what did not work →
  where the evidence is → attribution. The per-claim verification history moved into `claims.md`.

## Not yet done

- No Windows launcher is published (machine-specific, not portable — see `launcher/README.md`).
- The raw pinned-memory probe output and the kernel-timing trace were never archived, so those two numbers stay
  second-hand and are marked `[not published with the evidence]`.
