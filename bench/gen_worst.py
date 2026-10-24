"""Streams where the size estimate of the PR is badly wrong (task 4), in
/data/eval/worst/. All are compressed with igzip level 2.
  under1, under2: 8 MiB os.urandom head + 256 MiB zeros tail, one member / two
  underline1:     8 MiB os.urandom head + 256 MiB of one repeated line
  over1, over2:   256 MiB zeros head + 8 MiB os.urandom tail, one / two members
  overcap1:       64 MiB zeros head + 8 MiB os.urandom tail (the 8x cap)
"""
import os
import random

from isal import igzip

D = os.environ.get("WORST_DIR", "/data/eval/worst")
os.makedirs(D, exist_ok=True)
MiB = 1 << 20
rand = random.Random(290).randbytes(8 * MiB)
zeros = bytes(256 * MiB)
line = b"2026-10-24T12:00:00Z INFO worker-3 heartbeat ok\n"
lines = (line * (256 * MiB // len(line) + 1))[:256 * MiB]
specs = {
    "under1": [rand + zeros],
    "under2": [rand, zeros],
    "underline1": [rand + lines],
    "over1": [zeros + rand],
    "over2": [zeros, rand],
    "overcap1": [zeros[:64 * MiB] + rand],
}
for name, members in specs.items():
    gz = b"".join(igzip.compress(m, 2, mtime=0) for m in members)
    with open(f"{D}/{name}.gz", "wb") as f:
        f.write(gz)
    raw = sum(map(len, members))
    print(f"{name:<11} members {len(members)} raw {raw / MiB:.0f} MiB "
          f"gz {len(gz) / MiB:.2f} MiB ratio {raw / len(gz):.1f}")
