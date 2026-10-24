"""Free-threading stress test for readall() (run on CPython 3.14t).

1. Many threads, each with its own reader: igzip.decompress(), _GzipReader on
   bytes, and igzip.open(path).read() of the same data, many times each.
2. One shared reader: some threads call read(n) and others readall() at the
   same time. Each 8-byte block of the data holds its own offset, so every
   returned chunk shows where it came from. The check: chunks are aligned,
   match the data, and cover every byte exactly once.
Both for the private _GzipReader (its own lock) and for igzip.IGzipFile.
"""
import os
import random
import struct
import sys
import tempfile
import threading
import time

from isal import igzip, isal_zlib

N_BLOCKS = (4 << 20) // 8
DATA = b"".join(struct.pack("<Q", i) for i in range(N_BLOCKS))
# A second member, so readers also cross a member boundary. Its blocks
# continue the numbering, so every block in the stream is unique.
DATA2 = b"".join(struct.pack("<Q", i) for i in range(N_BLOCKS, N_BLOCKS + 8192))
GZ = igzip.compress(DATA, 1) + igzip.compress(DATA2, 1)
EXPECTED = DATA + DATA2
tmp = tempfile.NamedTemporaryFile(suffix=".gz", delete=False)
tmp.write(GZ)
tmp.close()
gil = sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True
print(sys.version.split()[0], "GIL enabled:", gil, flush=True)
failures = []


def separate(kind, iters):
    for _ in range(iters):
        if kind == "decompress":
            out = igzip.decompress(GZ)
        elif kind == "raw":
            out = isal_zlib._GzipReader(GZ).readall()
        else:
            with igzip.open(tmp.name) as f:
                out = f.read()
        if out != EXPECTED:
            failures.append(f"separate {kind}: wrong output")
            return


N_TOTAL = len(EXPECTED) // 8
non_contiguous = {"read": 0, "readall": 0}


def check_chunks(chunks, label):
    """Every 8-byte block of the stream must come back exactly once. Chunks
    that aren't one contiguous run of blocks are counted, not failed: on
    develop, another thread can read in the middle of a readall() call."""
    seen = bytearray(N_TOTAL)
    for kind, c in chunks:
        if not c:
            continue
        if len(c) % 8:
            failures.append(f"{label}: unaligned chunk of {len(c)} bytes")
            return
        idx = struct.unpack(f"<{len(c) // 8}Q", c)
        if any(i >= N_TOTAL for i in idx):
            failures.append(f"{label}: block index out of range")
            return
        for i in idx:
            if seen[i]:
                failures.append(f"{label}: block {i} returned twice")
                return
            seen[i] = 1
        if idx[-1] - idx[0] != len(idx) - 1:
            non_contiguous[kind] += 1
    if not all(seen):
        failures.append(f"{label}: {seen.count(0)} blocks never returned")


def shared(make_reader, label, threads=8):
    reader = make_reader()
    chunks = []
    lock = threading.Lock()
    barrier = threading.Barrier(threads)

    def work(i):
        rng = random.Random(i)
        barrier.wait()
        while True:
            if i % 2:
                kind = "read"
                b = reader.read(8 * rng.randrange(1, 8192))
            else:
                kind = "readall"
                # IGzipFile has no readall(); read() without a size calls it.
                b = (reader.readall() if hasattr(reader, "readall")
                     else reader.read())
            with lock:
                chunks.append((kind, b))
            if not b:
                return

    ts = [threading.Thread(target=work, args=(i,)) for i in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    check_chunks(chunks, label)


t0 = time.perf_counter()
ts = [threading.Thread(target=separate, args=(k, 25))
      for k in ("decompress", "raw", "file") for _ in range(6)]
for t in ts:
    t.start()
for t in ts:
    t.join()
print(f"separate readers: 18 threads x 25 calls in "
      f"{time.perf_counter() - t0:.1f} s", flush=True)
t0 = time.perf_counter()
for it in range(150):
    shared(lambda: isal_zlib._GzipReader(GZ), f"shared _GzipReader bytes #{it}")
    with open(tmp.name, "rb") as fp:
        shared(lambda: isal_zlib._GzipReader(fp, 32 * 1024),
               f"shared _GzipReader file #{it}")
    with igzip.open(tmp.name) as f:
        shared(lambda: f, f"shared IGzipFile #{it}")
    if failures:
        break
print(f"shared readers: {it + 1} x 3 tests in {time.perf_counter() - t0:.1f} s",
      flush=True)
print("non-contiguous chunks (another thread read in the middle):",
      non_contiguous, flush=True)
os.unlink(tmp.name)
if failures:
    print("FAILURES:", *failures[:10], sep="\n  ")
    sys.exit(1)
print("stress test passed")
