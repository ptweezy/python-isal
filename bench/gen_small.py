"""Generate small inputs for igzip.decompress() around glibc's mmap threshold.

Usage: gen_small.py <source dir> <out dir>

glibc serves allocations of 128 KiB or more with mmap() unless an earlier
free() of a bigger mmapped block raised the threshold. readall() shrinks its
first chunk to the output size before the result is freed, so the threshold
stays at 128 KiB, and every call that asks for a chunk of 128 KiB or more maps
and faults in fresh pages. The chunk is 4 (develop) or 10 (x10) times the
compressed size, so x10 crosses the threshold at 12.8 KiB of compressed data
instead of 32 KiB.

Each file mixes the PR's JSON event lines with random bytes, as in
gen_sweep.py, at about 3 and 6 to 1, for outputs from 8 KiB to 1 MiB. Writes
<out dir>/gz/s<ratio>.<size>.igzip2.gz and <out dir>/manifest.json in the
format of gen_sweep.py.
"""
import gzip
import hashlib
import json
import os
import random
import sys

from isal import igzip

SRC, OUT = sys.argv[1], sys.argv[2]
KiB = 1024
PIECE = 512
TARGETS = [3, 6]
SIZES = [8, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 1024]


def mix(base, other, share, size):
    parts, acc = [], 0.0
    for i in range(size // PIECE):
        acc += share
        src = base
        if acc >= 1.0:
            acc -= 1.0
            src = other
        parts.append(src[i * PIECE:(i + 1) * PIECE])
    return b"".join(parts)


def ratio(raw):
    return len(raw) / len(igzip.compress(raw, 2, mtime=0))


def search(base, other, target, size):
    lo, hi = 0.0, 1.0
    best = None
    for _ in range(40):
        mid = (lo + hi) / 2
        raw = mix(base, other, mid, size)
        r = ratio(raw)
        if best is None or abs(r - target) < abs(best[1] - target):
            best = (raw, r, mid)
        if abs(r - target) / target < 0.01:
            break
        if r > target:
            lo = mid
        else:
            hi = mid
    return best


def main():
    os.makedirs(f"{OUT}/gz", exist_ok=True)
    with gzip.open(f"{SRC}/json.raw.gz", "rb") as f:
        src = f.read()
    biggest = max(SIZES) * KiB
    # Start each size at a different offset, so that small files don't all
    # hold the same lines.
    base = (src * (2 * biggest // len(src) + 2))
    rnd = random.Random(290).randbytes(2 * biggest)
    manifest = {}
    for t in TARGETS:
        for size in SIZES:
            off = (size * 7919) % biggest
            raw, r, share = search(base[off:off + size * KiB],
                                   rnd[off:off + size * KiB], t, size * KiB)
            gz = igzip.compress(raw, 2, mtime=0)
            name = f"s{t}.{size}k"
            with open(f"{OUT}/gz/{name}.igzip2.gz", "wb") as f:
                f.write(gz)
            manifest[name] = {"target": t, "ratio": round(len(raw) / len(gz),
                                                          3),
                              "raw_size": len(raw), "gz_size": len(gz),
                              "share": share, "filler": "random",
                              "sha256": hashlib.sha256(raw).hexdigest()}
            print(name, manifest[name]["ratio"], len(gz), flush=True)
    with open(f"{OUT}/manifest.json", "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
