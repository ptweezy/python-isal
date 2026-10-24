"""Cost of a minor page fault on private anonymous memory, the kind malloc()
returns for large blocks. Copies N MiB from a buffer that is already faulted
into (a) a fresh private mapping (every page faults) and (b) the same mapping
again (no faults). (a - b) / pages is the cost per fault, including the
kernel zeroing the page. Uses MAP_PRIVATE|MAP_ANONYMOUS on Unix and
VirtualAlloc(MEM_COMMIT) on Windows.

(fault_cost.py used mmap.mmap(-1, n), which is MAP_SHARED: shared memory
faults, which cost more on some kernels. Don't use its numbers.)
Usage: fault_cost2.py [MiB] [rounds]"""
import ctypes
import mmap
import statistics
import sys
import time

mib = int(sys.argv[1]) if len(sys.argv) > 1 else 64
rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 15
n = mib << 20
pages = n // 4096
clock = time.perf_counter_ns
src = bytearray(b"\x5a") * n  # faulted, nonzero
src_addr = ctypes.addressof((ctypes.c_char * n).from_buffer(src))

if sys.platform == "win32":
    k32 = ctypes.WinDLL("kernel32")
    k32.VirtualAlloc.restype = ctypes.c_void_p
    k32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                 ctypes.c_uint32, ctypes.c_uint32]
    k32.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                ctypes.c_uint32]

    def fresh():
        a = k32.VirtualAlloc(None, n, 0x3000, 0x04)  # COMMIT|RESERVE, RW
        return a, lambda: k32.VirtualFree(a, 0, 0x8000)  # RELEASE
else:
    def fresh():
        m = mmap.mmap(-1, n, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
        buf = (ctypes.c_char * n).from_buffer(m)
        a = ctypes.addressof(buf)

        def close():
            nonlocal buf
            del buf
            m.close()
        return a, close

fault_ns, copy_ns = [], []
for _ in range(rounds):
    a, close = fresh()
    t = clock()
    ctypes.memmove(a, src_addr, n)
    t_fresh = clock() - t
    t = clock()
    ctypes.memmove(a, src_addr, n)
    t_warm = clock() - t
    close()
    fault_ns.append((t_fresh - t_warm) / pages)
    copy_ns.append(t_warm / pages)
print(f"{sys.platform}: private anonymous page fault {statistics.median(fault_ns):.0f}"
      f" ns median (min {min(fault_ns):.0f}, max {max(fault_ns):.0f}) per 4 KiB page;"
      f" copying 4 KiB into faulted memory {statistics.median(copy_ns):.0f} ns;"
      f" so writing fresh memory costs {(statistics.median(fault_ns) + statistics.median(copy_ns)) * 262144 / 1e9:.2f}"
      f" s/GiB vs {statistics.median(copy_ns) * 262144 / 1e9:.2f} s/GiB faulted")
