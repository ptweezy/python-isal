"""Summarize a full-matrix run with bootstrap confidence intervals.

Usage: full_summary.py [--clock cpu|wall] [--json out.json] [--title T]
                       results.jsonl...

Per case and config, the speedup of each round is develop time / config time,
paired by round: for warm calls, the median of the timed warm calls of each
process; for cold calls, the first call. The reported speedup is the median
over rounds, with a 95% bootstrap interval (rounds resampled 4,000 times).

develop-aa is the same develop build measured again. Its speedups show the
noise: the floor is the 95th percentile over cases of |log(A/A speedup)|. A
config's speedup counts as a real change only when its interval excludes 1
and it differs from 1 by more than the floor. The output also reports how
many A/A cases would pass that test, which should be close to none.
"""
import collections
import json
import math
import random
import statistics
import sys

args = sys.argv[1:]
clock, json_out, title, files = "cpu", None, "", []
i = 0
while i < len(args):
    if args[i] == "--clock":
        clock = args[i + 1]
        i += 2
    elif args[i] == "--json":
        json_out = args[i + 1]
        i += 2
    elif args[i] == "--title":
        title = args[i + 1]
        i += 2
    else:
        files.append(args[i])
        i += 1

runs = collections.defaultdict(lambda: collections.defaultdict(dict))
meta = {}
order = []
for fn in files:
    for line in open(fn):
        r = json.loads(line)
        c = r["case"]
        if c not in runs:
            order.append(c)
        runs[c][r["config"]][r["round"]] = r
        meta.setdefault("python", r.get("python"))
        meta.setdefault("cpu_unit", r.get("cpu_unit", "ns"))
# Every config other than develop, with the A/A control last.
VARIANTS = sorted({v for d in runs.values() for v in d} - {"develop"},
                  key=lambda v: (v == "develop-aa", v))
rng = random.Random(290)
B = 4000


def value(r, kind):
    if kind == "warm":
        w = r["warm_" + clock]
        return statistics.median(w) if w else None
    return r["cold_" + clock]


def speedup(case, v, kind):
    d, x = runs[case].get("develop", {}), runs[case].get(v, {})
    rs = []
    for k in d:
        if k in x:
            a, b = value(d[k], kind), value(x[k], kind)
            if a and b:
                rs.append(a / b)
    if len(rs) < 3:
        return None
    m = statistics.median(rs)
    boot = sorted(statistics.median(rng.choices(rs, k=len(rs)))
                  for _ in range(B))
    return m, boot[int(0.025 * B)], boot[int(0.975 * B) - 1], len(rs)


res = {c: {v: {k: speedup(c, v, k) for k in ("warm", "cold")}
           for v in VARIANTS if v in runs[c]} for c in order}
floor = {}
for k in ("warm", "cold"):
    aa = [abs(math.log(res[c]["develop-aa"][k][0])) for c in order
          if res[c].get("develop-aa", {}).get(k)]
    aa.sort()
    floor[k] = math.exp(aa[int(0.95 * (len(aa) - 1))]) if aa else 1.0


def real(s, k):
    if not s:
        return False
    m, lo, hi, _ = s
    return (lo > 1 or hi < 1) and abs(math.log(m)) > math.log(floor[k])


def fmt(s):
    return "" if not s else f"{s[0]:.2f} [{s[1]:.2f}-{s[2]:.2f}]"


def mark(s, k):
    if not real(s, k):
        return ""
    return " +" if s[0] > 1 else " **-**"


def med_field(case, v, field):
    vals = [r[field] for r in runs[case].get(v, {}).values()]
    if not vals:
        return None
    if isinstance(vals[0], list):
        vals = [statistics.median(x) for x in vals if x]
    return statistics.median(vals) if vals else None


def call_of(c):
    return c.split(".")[-1]


def size_of(c):
    return c.split(".")[1]


n_rounds = max(len(d) for cd in runs.values() for d in cd.values())
print(f"# {title or 'Full matrix'}\n")
print(f"Clock: {clock} ({meta.get('cpu_unit') if clock == 'cpu' else 'ns'}); "
      f"Python {meta.get('python')}; {len(order)} cases; up to {n_rounds} "
      f"rounds; configs: develop, {', '.join(VARIANTS)}.\n")
for k in ("warm", "cold"):
    aa_real = sum(real(res[c].get("develop-aa", {}).get(k), k) for c in order)
    print(f"- A/A noise floor ({k}): {floor[k]:.3f}; A/A cases flagged as a "
          f"change: {aa_real} of {len(order)}.")
print("\nSpeedup = develop time / config time, median over rounds, with a 95% "
      "bootstrap interval. `+` marks a real speedup and **-** a real "
      "slowdown (interval excludes 1 and beyond the A/A floor).\n")

print("## By call and size\n")
print("Median of the case speedups (min-max over cases); then the number of "
      "cases with a real speedup / real slowdown.\n")
groups = collections.OrderedDict()
for c in order:
    groups.setdefault((call_of(c), size_of(c)), []).append(c)
DISPLAY = VARIANTS
OWN = ["develop"] + [v for v in VARIANTS if v != "develop-aa"]
hdr = "| call | size | cases |"
for v in DISPLAY:
    hdr += f" {v} warm | {v} cold |"
print(hdr)
print("|" + "---|" * (hdr.count("|") - 1))
for (call, size), cs in groups.items():
    row = f"| {call} | {size} | {len(cs)} |"
    for v in DISPLAY:
        for k in ("warm", "cold"):
            ss = [res[c][v][k] for c in cs if res[c].get(v, {}).get(k)]
            if not ss:
                row += " |"
                continue
            ms = sorted(s[0] for s in ss)
            cell = f" {statistics.median(ms):.2f} ({ms[0]:.2f}-{ms[-1]:.2f})"
            up = sum(real(s, k) and s[0] > 1 for s in ss)
            down = sum(real(s, k) and s[0] < 1 for s in ss)
            row += f"{cell} {up}/{down} |"
    print(row)

for v in [v for v in VARIANTS if v != "develop-aa"]:
    print(f"\n## Real slowdowns: {v}\n")
    rows = [(c, k, res[c][v][k]) for c in order for k in ("warm", "cold")
            if res[c].get(v, {}).get(k) and real(res[c][v][k], k)
            and res[c][v][k][0] < 1]
    if not rows:
        print("None.")
        continue
    print("| case | warm/cold | speedup [95% CI] |")
    print("|---|---|---|")
    for c, k, s in sorted(rows, key=lambda t: t[2][0]):
        print(f"| {c} | {k} | {fmt(s)} |")

print("\n## All cases\n")
print("Faults: median minor page faults per warm call; dRSS: median growth "
      "of the peak RSS during the cold call, MiB.\n")
hdr = "| case | develop warm ms (wall) |"
for v in DISPLAY:
    hdr += f" {v} warm | {v} cold |"
hdr += f" faults {'/'.join(OWN)} | dRSS {'/'.join(OWN)} |"
print(hdr)
print("|" + "---|" * (hdr.count("|") - 1))
for c in order:
    dw = med_field(c, "develop", "warm_wall")
    row = f"| {c} | {dw / 1e6:.3f} |" if dw else f"| {c} | |"
    for v in DISPLAY:
        for k in ("warm", "cold"):
            s = res[c].get(v, {}).get(k)
            row += f" {fmt(s)}{mark(s, k)} |"
    fl = [med_field(c, v, "warm_minflt") for v in OWN]
    rss = [med_field(c, v, "rss_peak_growth_kb") for v in OWN]
    row += " " + "/".join("" if x is None else f"{x:.0f}" for x in fl) + " |"
    row += " " + "/".join("" if x is None else f"{x / 1024:.1f}"
                          for x in rss) + " |"
    print(row)

if json_out:
    with open(json_out, "w") as f:
        json.dump({"clock": clock, "floor": floor, "meta": meta,
                   "cases": {c: {v: {k: (list(s) if s else None) +
                                     ([real(s, k)] if s else [])
                                     for k, s in d.items()}
                                 for v, d in res[c].items()}
                             for c in order}}, f, indent=1)
