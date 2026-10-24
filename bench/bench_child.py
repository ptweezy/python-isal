"""One measurement in a fresh process. Prints one JSON line.

Usage: bench_child.py <call> <path> <warm calls> [--tracemalloc]

Calls: decompress (igzip.decompress of the file's bytes, read before timing),
read (igzip.open(path).read()), json_load (json.load(igzip.open(path))),
read131072, readline, iter (loops over igzip.open(path)), raw_readall
(isal_zlib._GzipReader(f, 32 KiB).readall()).

Sequence: one cold call (timed, with page faults and the growth of ru_maxrss),
one untimed warm-up call, then <warm> timed calls. With --tracemalloc, one call
under tracemalloc instead, reporting the traced peak.
"""
import json
import os
import sys
import time

import isal
from isal import igzip, isal_zlib

call, path, warm_n = sys.argv[1], sys.argv[2], int(sys.argv[3])
use_tracemalloc = "--tracemalloc" in sys.argv[4:]


def make(call, path):
    if call == "decompress":
        with open(path, "rb") as f:
            data = f.read()
        return lambda: len(igzip.decompress(data))
    if call == "read":
        def run():
            with igzip.open(path) as f:
                return len(f.read())
        return run
    if call == "json_load":
        def run():
            with igzip.open(path) as f:
                return len(json.load(f))
        return run
    if call == "read131072":
        def run():
            n = 0
            with igzip.open(path) as f:
                while True:
                    b = f.read(131072)
                    if not b:
                        return n
                    n += len(b)
        return run
    if call == "readline":
        def run():
            n = 0
            with igzip.open(path) as f:
                rl = f.readline
                while True:
                    b = rl()
                    if not b:
                        return n
                    n += len(b)
        return run
    if call == "iter":
        def run():
            n = 0
            with igzip.open(path) as f:
                for line in f:
                    n += len(line)
            return n
        return run
    if call == "raw_readall":
        def run():
            with open(path, "rb") as f:
                return len(isal_zlib._GzipReader(f, 32 * 1024).readall())
        return run
    raise SystemExit(f"unknown call {call}")


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]

    _psapi = ctypes.WinDLL("psapi")
    _k32 = ctypes.WinDLL("kernel32")
    _k32.GetCurrentProcess.restype = wintypes.HANDLE
    _psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC),
                                            wintypes.DWORD]
    _psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    def faults():
        # Windows counts soft and hard faults together; report them as minor.
        c = PMC()
        c.cb = ctypes.sizeof(PMC)
        _psapi.GetProcessMemoryInfo(_k32.GetCurrentProcess(), ctypes.byref(c),
                                    c.cb)
        return c.PageFaultCount, 0, c.PeakWorkingSetSize // 1024
else:
    import resource

    def faults():
        r = resource.getrusage(resource.RUSAGE_SELF)
        rss = r.ru_maxrss // 1024 if sys.platform == "darwin" else r.ru_maxrss
        return r.ru_minflt, r.ru_majflt, rss


def stats():
    f = getattr(isal_zlib, "_readall_stats", None)
    return list(f()) if f else None


fn = make(call, path)
info = {"isal_file": isal_zlib.__file__, "isal_version": isal.__version__,
        "python": sys.version.split()[0],
        "malloc_env": {k: v for k, v in os.environ.items()
                       if k.startswith("MALLOC_") or k == "GLIBC_TUNABLES"}}
if use_tracemalloc:
    import tracemalloc
    stats()
    tracemalloc.start()
    out_len = fn()
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    print(json.dumps(dict(info, out_len=out_len, tracemalloc_peak=peak,
                          stats=stats())))
    sys.exit()

stats()
f0, j0, rss0 = faults()
c0, w0 = time.thread_time_ns(), time.perf_counter_ns()
out_len = fn()
cold_cpu, cold_wall = time.thread_time_ns() - c0, time.perf_counter_ns() - w0
f1, j1, rss1 = faults()
cold_stats = stats()
fn()  # untimed warm-up
warm_cpu, warm_wall, warm_flt = [], [], []
for _ in range(warm_n):
    fa, _, _ = faults()
    c0, w0 = time.thread_time_ns(), time.perf_counter_ns()
    fn()
    warm_cpu.append(time.thread_time_ns() - c0)
    warm_wall.append(time.perf_counter_ns() - w0)
    warm_flt.append(faults()[0] - fa)
print(json.dumps(dict(info, out_len=out_len, cold_cpu=cold_cpu,
                      cold_wall=cold_wall, cold_minflt=f1 - f0,
                      cold_majflt=j1 - j0, rss_before_kb=rss0,
                      rss_peak_growth_kb=rss1 - rss0, cold_stats=cold_stats,
                      warm_cpu=warm_cpu, warm_wall=warm_wall,
                      warm_minflt=warm_flt)))
