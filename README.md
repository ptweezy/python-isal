# PR #290 evaluation runs (not part of the PR)

GitHub Actions workflow that builds python-isal develop (cfcf8b9) and PR #290
(b5e0495), plus ablation variants, on Windows (MSVC), macOS arm64, Linux, and
free-threaded CPython 3.14t; runs the test suites and interleaved benchmarks;
and uploads the results as artifacts. `data/` holds the PR's 4 and 32 MiB
text and JSON test files, compressed with isal level 2.
