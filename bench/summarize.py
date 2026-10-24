"""Summarize bench.py results as Markdown tables.

Usage: summarize.py [--base develop] [--cpu|--wall] results.jsonl...

Per case and config:
  warm: per process, the median of the timed warm calls; then the median and
        min-max over rounds.
  cold: the first call of each process; median and min-max over rounds.
  speedup: per round, base time / config time (paired by round); median and
        min-max over rounds.
  flt: minor page faults, cold call and median warm call.
  dRSS: growth of ru_maxrss during the cold call (MiB), median over rounds.
  tm: tracemalloc peak / output size, when measured.
"""
import collections
import json
import statistics
import sys

args = sys.argv[1:]
base = "develop"
clock = "cpu"
files = []
i = 0
while i < len(args):
    if args[i] == "--base":
        base = args[i + 1]
        i += 2
        continue
    if args[i] in ("--cpu", "--wall"):
        clock = args[i][2:]
    else:
        files.append(args[i])
    i += 1

rows = collections.defaultdict(lambda: collections.defaultdict(dict))
order = []
for fn in files:
    for line in open(fn):
        r = json.loads(line)
        key = r["case"]
        if key not in rows:
            order.append(key)
        rows[key][r["config"]][r["round"]] = r


def med(xs):
    return statistics.median(xs) if xs else float("nan")


def fmt_ms(ns):
    ms = ns / 1e6
    return f"{ms:.3f}" if ms < 1 else f"{ms:.2f}" if ms < 100 else f"{ms:.0f}"


def rng(xs, f):
    return f"{f(min(xs))}-{f(max(xs))}"


print(f"Clock: {clock} time. Speedup = {base} time / config time, paired by "
      "round.\n")
print("| case | config | warm ms med (min-max) | warm speedup med (min-max) | "
      "cold ms med (min-max) | cold speedup med (min-max) | flt cold / warm | "
      "dRSS MiB | tm peak / out |")
print("|---|---|---|---|---|---|---|---|---|")
for key in order:
    cfgs = rows[key]
    b = cfgs.get(base, {})
    for name, by_round in cfgs.items():
        rs = sorted(by_round)
        timed = [r for r in rs if "warm_" + clock in by_round[r]]
        tm = [by_round[r]["tracemalloc_peak"] / by_round[r]["out_len"]
              for r in rs if "tracemalloc_peak" in by_round[r]]
        if not timed:
            print(f"| {key} | {name} | | | | | | | {med(tm):.2f} |")
            continue
        warm = {r: med(by_round[r]["warm_" + clock]) for r in timed}
        cold = {r: by_round[r]["cold_" + clock] for r in timed}
        cells = [f"{fmt_ms(med(warm.values()))} ({rng(warm.values(), fmt_ms)})"]
        ws = [med(b[r]["warm_" + clock]) / warm[r] for r in timed
              if r in b and "warm_" + clock in b[r]]
        cells.append(f"{med(ws):.2f} ({rng(ws, lambda x: f'{x:.2f}')})"
                     if ws and name != base else "")
        cells.append(f"{fmt_ms(med(cold.values()))} "
                     f"({rng(cold.values(), fmt_ms)})")
        cs = [b[r]["cold_" + clock] / cold[r] for r in timed
              if r in b and "cold_" + clock in b[r]]
        cells.append(f"{med(cs):.2f} ({rng(cs, lambda x: f'{x:.2f}')})"
                     if cs and name != base else "")
        fc = med([by_round[r]["cold_minflt"] for r in timed])
        fw = med([med(by_round[r]["warm_minflt"]) for r in timed])
        cells.append(f"{fc:.0f} / {fw:.0f}")
        cells.append(f"{med([by_round[r]['rss_peak_growth_kb'] for r in timed]) / 1024:.1f}")
        cells.append(f"{med(tm):.2f}" if tm else "")
        print(f"| {key} | {name} | " + " | ".join(cells) + " |")
