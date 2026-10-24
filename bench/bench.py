"""Run benchmark rounds: a fresh process per measurement, configurations
interleaved in a new random order for every case of every round.

Usage: bench.py <spec.json> <out.jsonl>

spec = {
  "rounds": 7,
  "cpu": "2",                       # taskset CPU list for the children
  "configs": [{"name": "develop", "python": "/opt/v/develop/bin/python",
               "env": {"MALLOC_MMAP_THRESHOLD_": "131072"}}, ...],
  "cases": [{"id": "json21.4m.igzip2.decompress", "call": "decompress",
             "path": "/data/eval/gz/json21.4m.igzip2.gz", "warm": 5,
             "tracemalloc": false}, ...]
}
Each result line has the case id, config name, round, and the child's JSON,
which includes the loaded isal file and version (commit). The script stops if a
child loads an isal build other than the configured one.
"""
import json
import os
import random
import shutil
import subprocess
import sys
import time

spec_path, out_path = sys.argv[1], sys.argv[2]
spec = json.load(open(spec_path))
child = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "bench_child.py")
rng = random.Random(spec.get("seed", 1))
# Pin children to one CPU that this process may use (inside a container
# pinned with --cpuset-cpus, CPU 0 may not be one of them).
if hasattr(os, "sched_getaffinity") and shutil.which("taskset"):
    cpu = str(spec.get("cpu") or min(os.sched_getaffinity(0)))
    pin = ["taskset", "-c", cpu]
else:
    pin = []  # Windows and macOS runners: no pinning
start = time.time()
done = 0
total = spec["rounds"] * len(spec["cases"]) * len(spec["configs"])
with open(out_path, "a") as out:
    for rnd in range(spec["rounds"]):
        for case in spec["cases"]:
            configs = spec["configs"][:]
            rng.shuffle(configs)
            for cfg in configs:
                cmd = pin + [cfg["python"],
                       child, case["call"], case["path"],
                       str(case.get("warm", 5))]
                if case.get("tracemalloc"):
                    cmd.append("--tracemalloc")
                env = dict(os.environ, **cfg.get("env", {}))
                p = subprocess.run(cmd, capture_output=True, text=True,
                                   env=env, timeout=1800)
                if p.returncode:
                    sys.exit(f"child failed: {cmd}\n{p.stderr[-2000:]}")
                res = json.loads(p.stdout.strip().splitlines()[-1])
                venv = os.path.normcase(os.path.abspath(
                    os.path.dirname(os.path.dirname(cfg["python"]))))
                if not os.path.normcase(res["isal_file"]).startswith(venv):
                    sys.exit(f"wrong build loaded: {res['isal_file']} for {cfg}")
                out.write(json.dumps({"case": case["id"], "config": cfg["name"],
                                      "round": rnd, **res}) + "\n")
                out.flush()
                done += 1
        el = time.time() - start
        print(f"round {rnd + 1}/{spec['rounds']} done, {done}/{total} runs, "
              f"{el / 60:.1f} min", flush=True)
