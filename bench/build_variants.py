"""Build the evaluation variants on a CI runner, each in its own venv, with the
same compiler and flags. Usage: build_variants.py <work dir> <variant>...

Sources: <work>/src/develop (cfcf8b9) and <work>/src/pr (b5e0495), both with
the isa-l submodule. Variants derived from them get a patch from ci/patches or
ci/bench/patch_variants.py. Linux and macOS use CFLAGS="-O3 -DNDEBUG" like the
release wheels; Windows uses the setuptools defaults for MSVC, like the
release wheels. READALL_STATS builds add the define (CL on Windows).
"""
import os
import shutil
import subprocess
import sys

work = os.path.abspath(sys.argv[1])
variants = sys.argv[2:]
here = os.path.dirname(os.path.abspath(__file__))
patches = os.path.join(os.path.dirname(here), "patches")
BASE = {"develop": ("develop", None), "pr": ("pr", None),
        "nofstat": ("pr", "nofstat.diff"),
        "firstchunk": ("develop", "firstchunk.diff"),
        "stats-pr": ("pr", "stats-pr"), "stats-dev": ("develop", "stats-dev")}
SHA = {"develop": "cfcf8b9", "pr": "b5e0495"}
win = sys.platform == "win32"


def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


env = dict(os.environ, PYTHON_ISAL_BUILD_CACHE="1",
           PYTHON_ISAL_BUILD_CACHE_FILE=os.path.join(work, "isal_build_cache"))
for v in variants:
    base, patch = BASE[v]
    src = os.path.join(work, "src", base)
    if patch:
        dst = os.path.join(work, "src", v)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git"),
                        dirs_exist_ok=True)
        if patch.endswith(".diff"):
            run(["git", "apply", os.path.join(patches, patch)],
                cwd=dst)
        else:
            run([sys.executable, os.path.join(here, "patch_variants.py"),
                 patch, os.path.join(dst, "src", "isal", "isal_zlibmodule.c")])
        src = dst
    venv = os.path.join(work, "v", v)
    run([sys.executable, "-m", "venv", venv])
    py = os.path.join(venv, "Scripts" if win else "bin",
                      "python.exe" if win else "python")
    run([py, "-m", "pip", "install", "-q", "pytest"])
    benv = dict(env, SETUPTOOLS_SCM_PRETEND_VERSION=f"1.9.0.dev0+{v}.g{SHA[base]}")
    stats = v.startswith("stats-")
    if win:
        if stats:
            benv["CL"] = "/DREADALL_STATS"
    else:
        benv["CFLAGS"] = "-O3 -DNDEBUG" + (" -DREADALL_STATS" if stats else "")
    run([py, "-m", "pip", "install", "-q", "."], cwd=src, env=benv)
    run([py, "-c", "import isal, isal.isal_zlib as z; "
         "print(isal.__version__, z.__file__, hasattr(z, '_readall_stats'))"])
