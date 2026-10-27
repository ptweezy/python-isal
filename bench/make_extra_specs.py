"""Write the memory and counter passes for a timing spec.

Usage: make_extra_specs.py <timing spec> <venv dir>

For every decompress() and read() case of the timing spec, writes:
  <spec>_tm.json     one round of tracemalloc peaks for develop, pr and x10;
  <spec>_stats.json  one round with the READALL_STATS builds of the same three
                     (resizes, chunks and bytes grown per readall() call).
tracemalloc counts the bytes that were asked for, touched or not, so its peak
is also the most memory that the call can commit.
"""
import json
import os
import sys

spec_path, venvs = sys.argv[1], sys.argv[2]
win = sys.platform == "win32"


def config(name):
    return {"name": name, "env": {},
            "python": os.path.join(venvs, name, "Scripts" if win else "bin",
                                   "python.exe" if win else "python")}


spec = json.load(open(spec_path))
cases = [c for c in spec["cases"] if c["call"] in ("decompress", "read")]
base = os.path.splitext(spec_path)[0]
with open(base + "_tm.json", "w") as f:
    json.dump({"rounds": 1,
               "configs": [config(v) for v in ("develop", "pr", "x10")],
               "cases": [dict(c, id=c["id"] + ".tm", tracemalloc=True)
                         for c in cases]}, f, indent=1)
with open(base + "_stats.json", "w") as f:
    json.dump({"rounds": 1,
               "configs": [config(v) for v in ("stats-dev", "stats-pr",
                                               "stats-x10")],
               "cases": [dict(c, warm=0) for c in cases]}, f, indent=1)
print(base + "_tm.json", base + "_stats.json", len(cases), "cases each")
