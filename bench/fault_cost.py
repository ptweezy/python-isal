"""Cost of a minor page fault: touch every 4 KiB page of a fresh anonymous
mapping and time it (thread CPU time on Linux, perf_counter on Windows).
Also times a copy of the same amount of already-faulted memory, for scale.
Usage: fault_cost.py [MiB per round] [rounds]"""
import mmap
import sys
import time

mib = int(sys.argv[1]) if len(sys.argv) > 1 else 64
rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 15
n = mib << 20
pages = n // 4096
clock = time.perf_counter_ns if sys.platform == "win32" else time.thread_time_ns
res = []
for _ in range(rounds):
    m = mmap.mmap(-1, n)
    mv = memoryview(m)
    t = clock()
    for off in range(0, n, 4096):
        mv[off] = 1
    t = clock() - t
    mv.release()
    m.close()
    res.append(t / pages)
# Python loop overhead per touch, on memory that is already faulted.
m = mmap.mmap(-1, n)
mv = memoryview(m)
for off in range(0, n, 4096):
    mv[off] = 1
t = clock()
for off in range(0, n, 4096):
    mv[off] = 2
loop = (clock() - t) / pages
src = bytes(n)
t = clock()
dst = bytearray(src)
copy = (clock() - t) / n * (1 << 30) / 1e9
res.sort()
print(f"{sys.platform}: fault+touch {res[len(res) // 2]:.0f} ns/page median "
      f"(min {res[0]:.0f}, max {res[-1]:.0f}), loop overhead {loop:.0f} ns/page, "
      f"so about {res[len(res) // 2] - loop:.0f} ns per fault; bytearray copy of "
      f"faulted+fresh memory {copy:.2f} s/GiB")
