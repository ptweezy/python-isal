"""Generate the compression-ratio sweep for the x10 evaluation of PR #290.

Usage: gen_sweep.py <source dir> <out dir>

develop's readall() decompresses into chunks of 4 times the input buffer
size, and igzip.decompress() makes the input buffer as big as the compressed
data. So decompress() output fits in the first chunk only below a ratio of 4
to 1 (10 to 1 with x10), and above it all of the output is copied once more by
the join. This sweep puts data on both sides of both limits.

Each file mixes 2 KiB pieces of the PR's JSON event lines (json.raw.gz, about
21 to 1 with igzip level 2) with pieces of random bytes, for ratios below
that, or with pieces of zeros, for ratios above it. The pieces are spread
evenly, so the ratio is the same in every part of the stream. A binary search
on the share of random or zero pieces gets within 0.3% of each target ratio.

Writes <out dir>/gz/r<target>.<size>.igzip2.gz (igzip level 2, mtime 0) and
<out dir>/manifest.json with the target, the actual ratio, and the SHA-256 of
the raw data.
"""
import gzip
import hashlib
import json
import os
import random
import sys

from isal import igzip

SRC, OUT = sys.argv[1], sys.argv[2]
MiB = 1 << 20
PIECE = 2048
TARGETS = [2, 3, 3.6, 3.9, 4.1, 4.5, 6, 8, 9.5, 9.9, 10.1, 10.5, 12, 16, 24,
           32]
SIZES = [("4m", 4 * MiB), ("32m", 32 * MiB)]


def mix(base, other, share, size):
    """size bytes of base, with every piece where the running share passes a
    whole number taken from other instead."""
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


def search(base, other, target, size, below):
    """Find the share of other pieces that gives the target ratio. With
    random pieces, the ratio falls as the share grows; with zeros, it rises."""
    lo, hi = 0.0, 1.0
    best = None
    for _ in range(40):
        mid = (lo + hi) / 2
        raw = mix(base, other, mid, size)
        r = ratio(raw)
        if best is None or abs(r - target) < abs(best[1] - target):
            best = (raw, r, mid)
        if abs(r - target) / target < 0.003:
            break
        if (r > target) == below:
            lo = mid
        else:
            hi = mid
    return best


def main():
    os.makedirs(f"{OUT}/gz", exist_ok=True)
    with gzip.open(f"{SRC}/json.raw.gz", "rb") as f:
        src = f.read()
    biggest = max(s for _, s in SIZES)
    base = (src * (biggest // len(src) + 1))[:biggest]
    rnd = random.Random(290).randbytes(biggest)
    zeros = bytes(biggest)
    manifest = {}
    for label, size in SIZES:
        base_ratio = ratio(base[:size])
        for t in TARGETS:
            below = t < base_ratio
            raw, r, share = search(base, rnd if below else zeros, t, size,
                                   below)
            gz = igzip.compress(raw, 2, mtime=0)
            name = f"r{t:g}.{label}"
            with open(f"{OUT}/gz/{name}.igzip2.gz", "wb") as f:
                f.write(gz)
            manifest[name] = {"target": t, "ratio": round(len(raw) / len(gz),
                                                          3),
                              "raw_size": len(raw), "gz_size": len(gz),
                              "share": share,
                              "filler": "random" if below else "zeros",
                              "sha256": hashlib.sha256(raw).hexdigest()}
            print(name, manifest[name]["ratio"], manifest[name]["filler"],
                  f"{share:.5f}", flush=True)
    with open(f"{OUT}/manifest.json", "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
