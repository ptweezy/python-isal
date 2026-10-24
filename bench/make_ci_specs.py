"""Write the reduced CI benchmark specs. Usage: make_ci_specs.py <work dir>"""
import json
import os
import sys

work = os.path.abspath(sys.argv[1])
data = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data")
win = sys.platform == "win32"


def py(v):
    return os.path.join(work, "v", v, "Scripts" if win else "bin",
                        "python.exe" if win else "python")


def cfg(v):
    return {"name": v, "python": py(v), "env": {}}


main = [{"id": f"{k}.{s}.igzip2.{call}", "call": call,
         "path": os.path.join(data, f"{k}.{s}.igzip2.gz"),
         "warm": 5 if s == "4m" else 3}
        for k in ("text", "json21") for s in ("4m", "32m")
        for call in ("decompress", "read")]
worst = [{"id": f"worst.{w}.{call}", "call": call,
          "path": os.path.join(work, "worst", f"{w}.gz"), "warm": 2}
         for w in ("under1", "under2", "over1", "overcap1")
         for call in ("decompress", "read")]
specs = {
    "ci_main": {"rounds": 9, "configs": [cfg(v) for v in
                                         ("develop", "pr", "nofstat", "firstchunk")],
                "cases": main},
    "ci_worst": {"rounds": 5, "configs": [cfg("develop"), cfg("pr")],
                 "cases": worst},
    "ci_stats": {"rounds": 1, "configs": [cfg("stats-dev"), cfg("stats-pr")],
                 "cases": main + worst},
}
os.makedirs(os.path.join(work, "specs"), exist_ok=True)
for name, spec in specs.items():
    with open(os.path.join(work, "specs", name + ".json"), "w") as f:
        json.dump(spec, f, indent=1)
    print(name, len(spec["cases"]), "cases")
