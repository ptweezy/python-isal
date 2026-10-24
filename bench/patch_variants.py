"""Apply the PyPy and READALL_STATS edits to the variant worktrees.
Usage: patch_variants.py <kind> <path to isal_zlibmodule.c>"""
import sys

kind, p = sys.argv[1], sys.argv[2]
s = open(p, encoding="utf-8", newline="").read()


def sub(old, new):
    global s
    assert s.count(old) == 1, old
    s = s.replace(old, new)


STATS_DEF = """
#ifdef READALL_STATS
/* Benchmark builds only: count what readall() does. */
static Py_ssize_t readall_stat_resizes = 0;
static Py_ssize_t readall_stat_chunks = 0;
static Py_ssize_t readall_stat_grown_bytes = 0;

static PyObject *
isal_zlib__readall_stats(PyObject *module, PyObject *Py_UNUSED(ignore))
{
    PyObject *ret = Py_BuildValue("nnn", readall_stat_resizes,
                                  readall_stat_chunks,
                                  readall_stat_grown_bytes);
    readall_stat_resizes = readall_stat_chunks = readall_stat_grown_bytes = 0;
    return ret;
}
#endif

static PyObject *
GzipReader_readall("""
STATS_METHOD = """    ISAL_ZLIB_DECOMPRESSOBJ_METHODDEF,
#ifdef READALL_STATS
    {"_readall_stats", (PyCFunction)isal_zlib__readall_stats, METH_NOARGS,
     NULL},
#endif"""

if kind == "pypy":
    sub("""    int size_known = 1;
""", """#ifdef PYPY_VERSION
    /* Resizing a bytes object is slower than joining chunks on PyPy. */
    int size_known = 0;
#else
    int size_known = 1;
#endif
""")
elif kind == "stats-pr":
    sub("\nstatic PyObject *\nGzipReader_readall(", STATS_DEF)
    sub("    ISAL_ZLIB_DECOMPRESSOBJ_METHODDEF,", STATS_METHOD)
    sub("""            size = readall_new_size(written, consumed, left);
""", """            size = readall_new_size(written, consumed, left);
#ifdef READALL_STATS
            readall_stat_resizes += 1;
            readall_stat_grown_bytes += size;
#endif
""")
    sub("""        if (PyList_Append(chunks, result) < 0) {
            goto error;
        }
""", """        if (PyList_Append(chunks, result) < 0) {
            goto error;
        }
#ifdef READALL_STATS
        readall_stat_chunks += 1;
#endif
""")
elif kind == "stats-dev":
    sub("\nstatic PyObject *\nGzipReader_readall(", STATS_DEF)
    sub("    ISAL_ZLIB_DECOMPRESSOBJ_METHODDEF,", STATS_METHOD)
    sub("""        int ret = PyList_Append(chunk_list, chunk);
""", """#ifdef READALL_STATS
        readall_stat_chunks += 1;
#endif
        int ret = PyList_Append(chunk_list, chunk);
""")
assert "\r" not in s
open(p, "w", encoding="utf-8", newline="").write(s)
print("patched", kind)
