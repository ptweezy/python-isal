"""Generate the PR #290 evaluation datasets (CI version).

Usage: gen_datasets.py <source dir> <out dir> [kind...]
The source dir holds text.raw.gz, json.raw.gz, and fastq.raw.gz (the PR's
corpora). Writes <out dir>/gz/<kind>.<size>.<comp>.gz and
<out dir>/manifest.json, and compares the SHA-256 of every raw slice with
data/manifest_local.json from the local runs. Unlike the local version, it
doesn't keep the raw files. The rest of this docstring describes the local
version, which wrote to /data/eval.

Raw data (one base file per kind, 128 MiB, /data/eval/raw/<kind>.raw):
  text    the PR's corpus: first 32 MiB of CPython 3.12's Lib/**/*.py in sorted
          order (taken from /data/text.raw, which the PR's gen_corpus.py made
          in the python:3.12 image), repeated to 128 MiB
  json21  the PR's JSON event lines (from /data/json.raw), repeated
  fastq   the PR's synthetic FASTQ (from /data/fastq.raw), repeated
  json10, json5   JSON event lines with varied IDs, timestamps, and floats
  csv     sensor table with timestamps, IDs, floats
  log     web server access log (combined log format)
For json.load(), *json* kinds also get a JSON array version (<kind>a).

Compressed slices: /data/eval/gz/<kind>.<size>.<comp>.gz for sizes 64 KiB, 1,
2, 3, 4, 8, 32, 128 MiB and comp in igzip2 (isal level 2), gzip6 (GNU gzip -6
-n), zlib9 (zlib level 9, gzip container). A manifest with sizes, ratios and
SHA-256 of each raw slice goes to /data/eval/manifest.json.
"""
import gzip
import hashlib
import json
import os
import random
import subprocess
import sys
import zlib

from isal import igzip

SRC, OUT = sys.argv[1], sys.argv[2]
MiB = 1 << 20
BASE = 128 * MiB
SIZES = [("64k", 64 << 10), ("1m", MiB), ("2m", 2 * MiB), ("3m", 3 * MiB),
         ("4m", 4 * MiB), ("8m", 8 * MiB), ("32m", 32 * MiB),
         ("128m", 128 * MiB)]


def repeat_to(data, size):
    out = data * (size // len(data) + 1)
    return out[:size]


def json_varied(size, seed, precision, id_range, extra_fields,
                time_decimals=6, attributes=0):
    rng = random.Random(seed)
    parts, n = [], 0
    t = 1_761_200_000.0
    while n < size:
        t += rng.expovariate(20.0)
        ev = {"id": rng.randrange(id_range),
              "time": f"{t:.{time_decimals}f}",
              "entity_id": f"sensor.s{rng.randrange(id_range):x}",
              "value": round(rng.uniform(-1000, 1000), precision),
              "ok": rng.random() < 0.9}
        for k in range(extra_fields):
            ev[f"f{k}"] = round(rng.gauss(0, 100), precision)
        if attributes:
            ev["attributes"] = dict(list(ATTRIBUTES.items())[:attributes])
        b = json.dumps(ev, separators=(",", ":")).encode() + b"\n"
        parts.append(b)
        n += len(b)
    return b"".join(parts)[:size]


def csv_data(size, seed=11):
    rng = random.Random(seed)
    parts = [b"timestamp,sensor,temperature,humidity,pressure,status\n"]
    n = len(parts[0])
    t = 1_761_200_000
    while n < size:
        t += rng.randrange(1, 4)
        row = (f"{t},{rng.randrange(500)},{rng.gauss(21, 3):.2f},"
               f"{rng.uniform(20, 80):.1f},{rng.gauss(1013, 8):.1f},"
               f"{rng.choice(('OK', 'OK', 'OK', 'WARN', 'ERR'))}\n").encode()
        parts.append(row)
        n += len(row)
    return b"".join(parts)[:size]


def log_data(size, seed=12):
    rng = random.Random(seed)
    paths = ["/", "/index.html", "/api/v1/items", "/api/v1/users/{}",
             "/static/app.{}.js", "/static/style.css", "/login", "/search?q={}"]
    agents = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/141.0 Safari/537.36",
              "Mozilla/5.0 (X11; Linux x86_64; rv:144.0) Gecko/20100101 "
              "Firefox/144.0",
              "curl/8.15.0", "python-requests/2.33.0"]
    parts, n = [], 0
    t = 0
    while n < size:
        t += rng.randrange(0, 3)
        p = rng.choice(paths).format(rng.randrange(100000))
        line = (f"10.{rng.randrange(256)}.{rng.randrange(256)}."
                f"{rng.randrange(256)} - - [23/Oct/2026:{(t // 3600) % 24:02d}:"
                f"{(t // 60) % 60:02d}:{t % 60:02d} +0000] \"GET {p} HTTP/1.1\" "
                f"{rng.choice((200, 200, 200, 304, 404, 500))} "
                f"{rng.randrange(200, 50000)} \"-\" \"{rng.choice(agents)}\"\n")
        parts.append(line.encode())
        n += len(parts[-1])
    return b"".join(parts)[:size]


ATTRIBUTES = {"unit_of_measurement": "C", "device_class": "temperature",
              "state_class": "measurement",
              "friendly_name": "Temperature sensor"}
JSON10 = dict(precision=1, id_range=300, extra_fields=0, time_decimals=3,
              attributes=2)
JSON5 = dict(precision=2, id_range=1000, extra_fields=0)


def to_json_array(lines_data):
    lines = lines_data.rstrip(b"\n").split(b"\n")
    # Cut a partial last line, so the array is valid JSON.
    if lines and not lines[-1].endswith(b"}"):
        lines = lines[:-1]
    return b"[\n" + b",\n".join(lines) + b"\n]\n"


def compress(raw, comp):
    if comp == "igzip2":
        return igzip.compress(raw, 2, mtime=0)
    if comp == "gzip6":
        return subprocess.run(["gzip", "-6", "-n", "-c"], input=raw,
                              stdout=subprocess.PIPE, check=True).stdout
    if comp == "zlib9":
        c = zlib.compressobj(9, zlib.DEFLATED, 31)
        return c.compress(raw) + c.flush()
    raise ValueError(comp)


def main():
    os.makedirs(f"{OUT}/gz", exist_ok=True)
    kinds = sys.argv[3:] or ["text", "json21", "fastq", "json10", "json5",
                             "csv", "log"]
    manifest_path = f"{OUT}/manifest.json"
    manifest = (json.load(open(manifest_path))
                if os.path.exists(manifest_path) else {})
    for kind in kinds:
        if kind in ("text", "json21", "fastq"):
            src = {"text": "text", "json21": "json", "fastq": "fastq"}[kind]
            with gzip.open(f"{SRC}/{src}.raw.gz", "rb") as f:
                base = repeat_to(f.read(), BASE)
        elif kind == "json10":
            base = json_varied(BASE, 10, **JSON10)
        elif kind == "json5":
            base = json_varied(BASE, 5, **JSON5)
        elif kind == "csv":
            base = csv_data(BASE)
        elif kind == "log":
            base = log_data(BASE)
        variants = [(kind, base)]
        if kind.startswith("json"):
            variants.append((kind + "a", None))
        for name, data in variants:
            for label, size in SIZES:
                raw = data[:size] if data is not None else to_json_array(
                    base[:size])
                entry = {"raw_size": len(raw),
                         "sha256": hashlib.sha256(raw).hexdigest()}
                ref = LOCAL.get(f"{name}.{label}", {}).get("sha256")
                entry["matches_local"] = ref == entry["sha256"]
                for comp in ("igzip2", "gzip6", "zlib9"):
                    gz = compress(raw, comp)
                    with open(f"{OUT}/gz/{name}.{label}.{comp}.gz", "wb") as f:
                        f.write(gz)
                    entry[comp] = {"gz_size": len(gz),
                                   "ratio": round(len(raw) / len(gz), 2)}
                manifest[f"{name}.{label}"] = entry
                print(name, label, {c: entry[c]["ratio"] for c in
                                    ("igzip2", "gzip6", "zlib9")},
                      "same raw data as locally" if entry["matches_local"]
                      else "RAW DATA DIFFERS FROM THE LOCAL RUN", flush=True)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=1, sort_keys=True)


LOCAL = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "data", "manifest_local.json")))

if __name__ == "__main__":
    main()
