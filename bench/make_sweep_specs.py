"""Write the spec for the compression-ratio sweep (see gen_sweep.py).

Usage: make_sweep_specs.py <sweep dir> <venv dir> <out spec> <rounds>

Configs: develop, develop-aa, pr, and x10, as in make_full_specs.py. Cases:
igzip.decompress() and igzip.open(path).read() of every sweep file.
"""
import json
import os
import sys

sweep, venvs, out, rounds = sys.argv[1], sys.argv[2], sys.argv[3], int(
    sys.argv[4])
win = sys.platform == "win32"


def python(name):
    return os.path.join(venvs, name, "Scripts" if win else "bin",
                        "python.exe" if win else "python")


manifest = json.load(open(os.path.join(sweep, "manifest.json")))
names = sorted(manifest, key=lambda n: (manifest[n]["raw_size"],
                                        manifest[n]["target"]))
configs = [{"name": n, "python": python(p), "env": {}}
           for n, p in (("develop", "develop"), ("develop-aa", "develop"),
                        ("pr", "pr"), ("x10", "x10"))]
cases = [{"id": f"{n}.igzip2.{call}", "call": call,
          "path": os.path.join(sweep, "gz", f"{n}.igzip2.gz"),
          "warm": 3 if n.endswith(".32m") else 5}
         for n in names for call in ("decompress", "read")]
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
with open(out, "w") as f:
    json.dump({"rounds": rounds, "configs": configs, "cases": cases}, f,
              indent=1)
print(out, len(cases), "cases x", len(configs), "configs x", rounds, "rounds")
