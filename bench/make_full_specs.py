"""Write the spec for the full benchmark matrix of PR #290.

Usage: make_full_specs.py <gz dir> <venv dir> <out spec> <rounds> [kind...]

Configs: develop, develop-aa (the same develop build again, an A/A control
for the noise floor), pr, and min2x (the PR with a minimum growth step of 2).
Each venv is <venv dir>/<name>, with python in Scripts/ on Windows and bin/
elsewhere. Cases, for each kind given (default: all seven):
  - igzip.decompress() and igzip.open(path).read() for 3 compressors and 8
    sizes from 64 KiB to 128 MiB;
  - json.load(igzip.open(path)) of the JSON array versions (json kinds only),
    igzip level 2 and gzip -6, up to 32 MiB;
  - read(131072), readline() and line iteration of 32 MiB (text and fastq).
"""
import json
import os
import sys

gz, venvs, out, rounds = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
kinds = sys.argv[5:] or ["text", "json21", "json10", "json5", "fastq", "csv",
                         "log"]
SIZES = ["64k", "1m", "2m", "3m", "4m", "8m", "32m", "128m"]
COMPS = ["igzip2", "gzip6", "zlib9"]
win = sys.platform == "win32"


def python(name):
    return os.path.join(venvs, name, "Scripts" if win else "bin",
                        "python.exe" if win else "python")


def case(kind, size, comp, call):
    return {"id": f"{kind}.{size}.{comp}.{call}", "call": call,
            "path": os.path.join(gz, f"{kind}.{size}.{comp}.gz"),
            "warm": 3 if size in ("32m", "128m") else 5}


configs = [{"name": "develop", "python": python("develop"), "env": {}},
           {"name": "develop-aa", "python": python("develop"), "env": {}},
           {"name": "pr", "python": python("pr"), "env": {}},
           {"name": "min2x", "python": python("min2x"), "env": {}}]
cases = []
for k in kinds:
    cases += [case(k, s, c, call) for c in COMPS for s in SIZES
              for call in ("decompress", "read")]
    if k.startswith("json"):
        cases += [case(k + "a", s, c, "json_load") for c in ("igzip2", "gzip6")
                  for s in SIZES if s != "128m"]
    if k in ("text", "fastq"):
        cases += [case(k, "32m", c, call) for c in ("igzip2", "gzip6")
                  for call in ("read131072", "readline", "iter")]
missing = [c["path"] for c in cases if not os.path.exists(c["path"])]
if missing:
    sys.exit(f"{len(missing)} data files missing, for example {missing[0]}")
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
with open(out, "w") as f:
    json.dump({"rounds": rounds, "configs": configs, "cases": cases}, f,
              indent=1)
print(out, len(cases), "cases x", len(configs), "configs x", rounds, "rounds")
