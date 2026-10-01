# Generate the README benchmark figure + the GitHub social-preview card as HTML
# (plain stdlib only; rasterised later by headless Edge).
# Usage: python gen_chart.py <out_dir> <csv_path>
import csv
import math
import os
import sys
import html

OUT = sys.argv[1]
CSV = sys.argv[2]
os.makedirs(OUT, exist_ok=True)

rows = []
with open(CSV, newline="", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        def num(k):
            v = (r.get(k) or "").strip()
            try:
                return float(v)
            except ValueError:
                return None
        rows.append(dict(
            req=int(r["req"]),
            prompt=num("prompt_tokens"),
            decode=num("decode_tok_s"),
            ttft=num("ttft_s"),
            cache=num("cache_pct"),
            finish=r.get("finish", ""),
        ))

# --- label sets, taken with the same rules the README states ---------------
pts_a = [r for r in rows if r["prompt"] and r["decode"]]
hits = [r for r in rows if r["cache"] is not None and r["cache"] >= 99 and r["ttft"]]
misses = [r for r in rows if r["prompt"] and r["prompt"] >= 40000 and r["ttft"]
          and (r["cache"] or 0) < 1.0]


def rng(v):
    return min(v), max(v)


print("panel A n =", len(pts_a))
print("hits  n =", len(hits), "ttft", rng([r["ttft"] for r in hits]))
print("miss  n =", len(misses), "ttft", rng([r["ttft"] for r in misses]))

BLUE = "#2f81f7"
RED = "#d73a4a"
GREEN = "#1a7f37"
INK = "#1f2328"
MUTED = "#59636e"
GRID = "#e6e9ee"

W, H = 1200, 560
PX0, PX1 = 58, 566          # panel A plot box
PY0, PY1 = 96, 452
QX0, QX1 = 712, 1140        # panel B plot box


def esc(s):
    return html.escape(str(s))


# ---------------- panel A: decode vs prompt depth --------------------------
XLO, XHI = math.log10(40), math.log10(260000)
YLO, YHI = 0.0, 100.0


def ax(p):
    return PX0 + (math.log10(max(p, 40)) - XLO) / (XHI - XLO) * (PX1 - PX0)


def ay(d):
    return PY1 - (d - YLO) / (YHI - YLO) * (PY1 - PY0)


sv = []
sv.append(f'<rect x="{PX0}" y="{PY0}" width="{PX1-PX0}" height="{PY1-PY0}" fill="#fff" stroke="{GRID}"/>')
for yt in (0, 20, 40, 60, 80, 100):
    y = ay(yt)
    sv.append(f'<line x1="{PX0}" y1="{y:.1f}" x2="{PX1}" y2="{y:.1f}" stroke="{GRID}"/>')
    sv.append(f'<text x="{PX0-9}" y="{y+4:.1f}" text-anchor="end" class="tick">{yt}</text>')
for xt in (100, 1000, 10000, 100000, 200000):
    x = ax(xt)
    sv.append(f'<line x1="{x:.1f}" y1="{PY0}" x2="{x:.1f}" y2="{PY1}" stroke="{GRID}"/>')
    lab = f"{xt//1000}k" if xt >= 1000 else str(xt)
    sv.append(f'<text x="{x:.1f}" y="{PY1+18}" text-anchor="middle" class="tick">{lab}</text>')
sv.append(f'<text x="{(PX0+PX1)/2:.0f}" y="{PY1+40}" text-anchor="middle" class="axlab">prompt tokens (log scale)</text>')
sv.append(f'<text x="{PX0-42}" y="{(PY0+PY1)/2:.0f}" text-anchor="middle" class="axlab" transform="rotate(-90 {PX0-42} {(PY0+PY1)/2:.0f})">decode tok/s</text>')

for yv, col, lab in ((56.8, GREEN, "median @ 40k prompt: 56.8 tok/s"),
                     (46.6, RED, "median @ 200k prompt: 46.6 tok/s")):
    y = ay(yv)
    sv.append(f'<line x1="{PX0}" y1="{y:.1f}" x2="{PX1}" y2="{y:.1f}" stroke="{col}" stroke-dasharray="6 4" stroke-width="1.4" opacity=".75"/>')

ly = PY1 - 54
for yv, col, lab in ((56.8, GREEN, "median @ 40k prompt: 56.8 tok/s"),
                     (46.6, RED, "median @ 200k prompt: 46.6 tok/s")):
    sv.append(f'<line x1="{PX0+12}" y1="{ly}" x2="{PX0+34}" y2="{ly}" stroke="{col}" stroke-dasharray="6 4" stroke-width="1.6"/>')
    sv.append(f'<text x="{PX0+42}" y="{ly+4}" class="note" fill="{col}">{esc(lab)}</text>')
    ly += 22

for r in pts_a:
    sv.append(f'<circle cx="{ax(r["prompt"]):.1f}" cy="{ay(r["decode"]):.1f}" r="4.2" fill="{BLUE}" fill-opacity=".8" stroke="#fff" stroke-width="1"/>')

sv.append(f'<text x="{PX0+10}" y="{PY0+22}" class="note2" fill="{MUTED}">53 real agent requests &#183; no collapse at any depth</text>')
sv.append(f'<text x="{PX0+10}" y="{PY0+40}" class="note2" fill="{MUTED}">200k band: 42.3&#8211;52.1 tok/s</text>')

sv.append(f'<text x="{PX0}" y="{PY0-44}" class="ptitle">Decode speed vs prompt depth</text>')
sv.append(f'<text x="{PX0}" y="{PY0-24}" class="psub">One real 53-request agent session &#183; 200k band holds 42.3&#8211;52.1 tok/s</text>')

# ---------------- panel B: TTFT hit vs miss -------------------------------
BYLO, BYHI = 0.4, 420.0
b1, b2 = QX0 + 96, QX1 - 96
BW = 62


def by(t):
    return PY1 - (math.log10(t) - math.log10(BYLO)) / (math.log10(BYHI) - math.log10(BYLO)) * (PY1 - PY0)


sv.append(f'<rect x="{QX0}" y="{PY0}" width="{QX1-QX0}" height="{PY1-PY0}" fill="#fff" stroke="{GRID}"/>')
for yt, lab in ((0.5, "0.5 s"), (1, "1 s"), (5, "5 s"), (10, "10 s"), (60, "1 min"), (300, "5 min")):
    y = by(yt)
    sv.append(f'<line x1="{QX0}" y1="{y:.1f}" x2="{QX1}" y2="{y:.1f}" stroke="{GRID}"/>')
    sv.append(f'<text x="{QX0-9}" y="{y+4:.1f}" text-anchor="end" class="tick">{lab}</text>')


def strip(cx, vals, col):
    out = []
    n = len(vals)
    for i, r in enumerate(sorted(vals, key=lambda z: z[1])):
        jitter = ((i % 5) - 2) * 11 + (7 if (i // 5) % 2 else -7)
        out.append(f'<circle cx="{cx+jitter:.1f}" cy="{by(r[1]):.1f}" r="5.2" fill="{col}" fill-opacity=".62" stroke="#fff" stroke-width="1"/>')
    return out


hvals = [(r["req"], r["ttft"]) for r in hits]
mvals = [(r["req"], r["ttft"]) for r in misses]
sv += strip(b1, hvals, GREEN)
sv += strip(b2, mvals, RED)

# group frames + labels
sv.append(f'<line x1="{b1-BW}" y1="{PY1}" x2="{b1+BW}" y2="{PY1}" stroke="{INK}" stroke-width="1.4"/>')
sv.append(f'<line x1="{b2-BW}" y1="{PY1}" x2="{b2+BW}" y2="{PY1}" stroke="{INK}" stroke-width="1.4"/>')
sv.append(f'<text x="{b1}" y="{PY1+22}" text-anchor="middle" class="grouplab" fill="{GREEN}">cache hit (reuse &#8805;99%)</text>')
sv.append(f'<text x="{b1}" y="{PY1+40}" text-anchor="middle" class="tick">n = {len(hvals)} &#183; {min(v for _, v in hvals):.2f} &#8211; {max(v for _, v in hvals):.2f} s</text>')
sv.append(f'<text x="{b2}" y="{PY1+22}" text-anchor="middle" class="grouplab" fill="{RED}">cache miss, prompt &#8805;40k</text>')
sv.append(f'<text x="{b2}" y="{PY1+40}" text-anchor="middle" class="tick">n = {len(mvals)} &#183; 43.1 s &#8211; 4 m 44 s</text>')

sv.append(f'<text x="{QX0}" y="{PY0-44}" class="ptitle">Time to first token</text>')
sv.append(f'<text x="{QX0}" y="{PY0-24}" class="psub">A miss re-prefills the whole prompt (the 5-minute freeze)</text>')

CSS = """
body{margin:0;background:#fff}
text{font-family:'Segoe UI',Arial,sans-serif;fill:#1f2328}
.tick{font-size:11.5px;fill:#59636e}
.axlab{font-size:12px;fill:#59636e}
.note{font-size:12.5px;font-weight:600}
.note2{font-size:12.5px}
.ptitle{font-size:18px;font-weight:700}
.psub{font-size:12.5px;fill:#59636e}
.grouplab{font-size:13px;font-weight:700}
.ftr{font-size:11.5px;fill:#8b949e}
"""

fig = f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
{''.join(sv)}
<text x="{PX0}" y="{H-10}" class="ftr">Source: data/session-53-requests.csv &#183; Tesla V100-SXM2-32GB (sm_70) &#183; Qwen3.8-27B &#183; NInfer &#183; int8 KV &#183; MTP K=3</text>
<text x="{QX1}" y="{H-10}" text-anchor="end" class="ftr">taskeee/ninfer-v100-sm70-decode</text>
</svg></body></html>"""
open(os.path.join(OUT, "chart.html"), "w", encoding="utf-8").write(fig)

# ---------------- social preview card 1280x640 ----------------------------
SW, SH = 1280, 640
social = f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}
body{{margin:0;width:{SW}px;height:{SH}px;background:#0d1117;color:#e6edf3;
font-family:'Segoe UI',Arial,sans-serif;overflow:hidden;position:relative}}
.glow{{position:absolute;width:900px;height:900px;left:-260px;top:-460px;border-radius:50%;
background:radial-gradient(circle,rgba(47,129,247,.42),rgba(47,129,247,0) 62%)}}
.glow2{{position:absolute;width:760px;height:760px;right:-220px;bottom:-420px;border-radius:50%;
background:radial-gradient(circle,rgba(215,58,74,.34),rgba(215,58,74,0) 62%)}}
.wrap{{position:relative;padding:58px 64px;height:100%;display:flex;flex-direction:column;justify-content:space-between}}
.kicker{{font-size:22px;letter-spacing:.14em;text-transform:uppercase;color:#7d8590;font-weight:600}}
h1{{font-size:62px;line-height:1.08;margin:18px 0 0;font-weight:800;letter-spacing:-1.2px}}
h1 em{{font-style:normal;color:#58a6ff}}
.sub{{font-size:25px;color:#adbac7;margin-top:20px;line-height:1.4}}
.metrics{{display:flex;gap:22px}}
.m{{flex:1;background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.13);border-radius:16px;padding:20px 22px}}
.m b{{display:block;font-size:40px;font-weight:800;letter-spacing:-.8px}}
.m span{{display:block;font-size:17px;color:#adbac7;margin-top:8px;line-height:1.3}}
.b1 b{{color:#58a6ff}} .b2 b{{color:#3fb950}} .b3 b{{color:#f0883e}}
.foot{{display:flex;justify-content:space-between;align-items:center;font-size:20px;color:#7d8590;font-weight:600}}
</style></head><body>
<div class="glow"></div><div class="glow2"></div>
<div class="wrap">
  <div>
    <div class="kicker">sm_70 &#183; Tesla V100 32GB &#183; single card</div>
    <h1>A 2017 GPU running a 2026 <em>27B long-context agent</em></h1>
    <div class="sub">Qwen3.8-27B &#183; 200k-token context &#183; sm70 decode kernel + KV cache tuning &#183; raw engine logs included</div>
  </div>
  <div class="metrics">
    <div class="m b1"><b>42.3&#8211;89.4</b><span>tok/s decode, 200k-token prompts included</span></div>
    <div class="m b2"><b>0.54 s</b><span>time to first token on a cache hit (up to 4 m 44 s on a miss)</span></div>
    <div class="m b3"><b>53 / 53</b><span>real agent requests finished, zero errors, zero OOM</span></div>
  </div>
  <div class="foot"><span>github.com/taskeee/ninfer-v100-sm70-decode</span><span>published by an AI on the owner's behalf</span></div>
</div></body></html>"""
open(os.path.join(OUT, "social.html"), "w", encoding="utf-8").write(social)
print("wrote", os.path.join(OUT, "chart.html"), "and social.html")
