# PR #290 evaluation runs (not part of the PR)

GitHub Actions workflow that builds python-isal develop (cfcf8b9) and PR #290
(b5e0495), plus ablation variants, on Windows (MSVC), macOS arm64, Linux, and
free-threaded CPython 3.14t; runs the test suites and interleaved benchmarks;
and uploads the results as artifacts. `data/` holds the PR's 4 and 32 MiB
text and JSON test files, compressed with isal level 2.

## Full matrix (branch eval-pr290-full)

Workflow `eval-pr290-full.yml` runs the whole benchmark matrix on Ubuntu,
Windows (MSVC), and macOS arm64 runners, one job per OS and data kind:
develop, an A/A copy of develop, the PR, and variant e (minimum growth step
2), 11 rounds, thread CPU time (`QueryThreadCycleTime()` on Windows) and wall
time. `data/src` holds the PR's text, JSON, and FASTQ corpora (gzip -9);
`bench/gen_datasets.py` rebuilds every data set from them and checks each raw
slice against `data/manifest_local.json` from the local runs.
`bench/full_summary.py` reports paired speedups with 95% bootstrap intervals
and an A/A noise floor.
