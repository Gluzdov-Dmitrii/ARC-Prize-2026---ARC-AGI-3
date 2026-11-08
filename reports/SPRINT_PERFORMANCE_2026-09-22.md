# S10 instrumentation performance audit — 2026-09-22

**Updated finding: the measured local instrumentation regression is resolved by the S10 snapshot cache.** On the same-path atomic-replacement benchmark, cached S10 performs two actual reads per modeled request, matching S4, and its measured instrumentation is faster. This result does not establish a GPU/LLM latency or game-score improvement. The original uncached measurements remain below for traceability.

## Cached revision verification

Measured S10 SHA-256: `a247847f4a4b92eefab337940a13a7070b37c4298090aea4ec2e30f91cd6e7ec`. Five randomized repetitions per profile/case; medians in milliseconds:

| History entries | S4 instrumentation wall | Cached S10 instrumentation wall | Difference | S10 / S4 | S4 CPU | S10 CPU |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 222.7 | 133.7 | −89.0 | 0.60× | 218.8 | 125.0 |
| 500 | 1,080.2 | 574.1 | −506.1 | 0.53× | 1,062.5 | 562.5 |

The real default-loader S10 wrappers were used without injecting a synthetic loader. `Path.read_text` was counted at the filesystem layer: **exactly two reads per cycle for both S4 and S10**, including the initial snapshot read and mandatory post-action refresh. Eleven additional `_ensure_session` calls against the unchanged file performed **zero reads**. Their median costs were 0.457 ms at 100 history entries and 0.906 ms at 500 entries. The stored final snapshot was checked against the post-action step; all 12 warm/measured S10 transitions were recognized and no internal error was reported.

The script uses one actual runtime filepath per case. Before each cycle it copies and atomically installs the before-state outside timing, and stages the after-state. During the stub action, timing is paused while the staged file atomically replaces the active path; this 1.5–5.6 ms rename operation is excluded for both profiles. The actual cache therefore observes same-path file replacement. The five outer `_ensure_session` call sites and inner guarded call match the earlier source-derived path. Full state payloads are still generated with the unchanged harness writer.

Reproduce with `python tmp/sprint_20260922/performance_cached_audit.py`. It verifies the source hash and completed in 17.57 seconds. Raw timings and read counts: `tmp/sprint_20260922/performance_results_cached.json`; exact measured source snapshot: `tmp/sprint_20260922/performance_s10_cached_source.py`. The script retains S4 printing into a local `StringIO` for both profiles instead of console transport; the print operation still runs. The original v1 benchmark is preserved as `performance_audit_v1.py` and its results as `performance_results_v1.json`.

These timings compare both current profiles within one run. Host conditions and measurement details changed from the uncached run, so subtracting old absolute timings from new timings would not isolate the cache benefit. Read-count reduction from seven to two establishes the intended mechanism. Saturated books, real model-request distributions, concurrent 28-game serving, Linux filesystem behavior and total competition runtime remain unmeasured.

## Original uncached finding

The original S10 snapshot loader and two-read tool wrapper were faster than S4, but `_ensure_session` introduced repeated whole-file reads. Its source-derived one-request/one-tool path added **75–653 ms** across the selected cases. That prompted the cache repair above.

## Measurements

Warm-cache Windows timings, medians in milliseconds. Each row uses the same state files and randomly interleaved operation order for both profiles. CPU time accompanies wall time because the host was not idle and individual measurements varied substantially.

| History entries | JSON size, decimal MB | Repeats | S4 loader | S10 snapshot | S4 tool hook | S10 tool hook |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.74 | 11 | 60.1 | 27.6 | 130.1 | 67.0 |
| 100 | 6.94 | 7 | 281.6 | 136.5 | 531.5 | 308.1 |
| 500 | 34.49 | 5 | 526.6 | 318.9 | 1,141.9 | 722.9 |

| History entries | S4 one-request instrumentation | S10 one-request instrumentation | Added wall time | S10 / S4 | S4 CPU | S10 CPU |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 150.4 | 225.3 | +74.9 | 1.50× | 62.5 | 125.0 |
| 100 | 548.8 | 1,007.4 | +458.6 | 1.84× | 437.5 | 875.0 |
| 500 | 1,298.9 | 1,951.5 | +652.6 | 1.50× | 1,296.9 | 1,937.5 |

The S4 `_ensure_session` call itself is about 0.02–0.04 ms here. The S10 wrapper adds a full snapshot read: median 32.1 / 137.7 / 299.2 ms at 10 / 100 / 500 history entries. At 500 entries, complete-path wall ranges were S4 1,006.6–1,393.4 ms and S10 1,852.8–3,135.1 ms. These small samples are descriptive; ratios are not a precision or significance claim.

## Why the complete path differs

Exact S4 `duck_load_grid` invokes the original `load_runtime_state`, which decodes JSON and normalizes every historical grid. S10 `load_snapshot` still decodes the whole JSON but normalizes only the current grid, scans action history for RESET markers, and hashes the current semantic state. That makes a single read cheaper.

For a normal `analyze()` call with one model request, one Python tool, and persistent history, inspected `ToolAgent` source contains five `_ensure_session` calls outside the S10 `in_tool` guard:

1. `analyze` entry.
2. Initial `_tools` call while trimming messages.
3. `_tools` in the model-request loop.
4. `_dispatch_tool` before entering the wrapped Python tool.
5. `_tools` in the `finally` block while retaining history.

The inner `_run_python_tool` call to `_ensure_session` is guarded and does not add a snapshot read. Therefore the measured instrumentation path has **two S4 loads versus seven S10 snapshots**. Additional requests/tools change that count; this is a source-derived representative path, not an observed model trace.

## Reproduction and limits

Run `python tmp/sprint_20260922/performance_audit.py` from the repository root. The completed run took 104.84 seconds wall time and reported zero S10 internal errors. Generated states are `tmp/sprint_20260922/performance_state_*`; raw samples, platform/Python details, timer values, source hashes and call-count assumptions are in `tmp/sprint_20260922/performance_results.json`.

The script extracts **exact embedded S4 source from the original parent notebook** and the unchanged runtime loader/serializer and `_ensure_session` method from the inspected harness. Only the unused ASCII formatting import is stubbed. It uses the actual runtime serializer with `indent=2`, 64×64 grids, full per-entry historical grids, and occasional explicit RESET entries. State construction and writes occur outside the timed region. The tool body is a local stub returning a fresh single-action summary; both real instrumentation wrappers run around it. Common base-harness loads, prompt generation, engine work, model serving and network work are excluded. S4's original repeated-confirmation printing remains in its timed wrapper.

Repeated synthetic transitions roll S10's step back between benchmark iterations, triggering its scope reset; this isolates instrumentation cost and is not a policy-quality test or a benchmark of a saturated memory book. Windows filesystem/cache behavior, host scheduling and CPU clock changes limit transfer to Kaggle/Linux. No GPU, model, API, remote job or scored game was used. No `src` or `tests` files were changed by this audit.

The measured S10 source SHA-256 is `106cb58c04e244087dbeaf10366829b40c0c961b499df843a9dec23471b5f191`. Parent embedded S4 source SHA-256 is `0c0d789783fbd944499cae6f5e37b46d24dea8077755a4ec892d35dc2486f07a`. If S10 is amended, these timings describe the original version only.

## Original recommendation and disposition

The recommendation was to reuse snapshots while the runtime file is unchanged, preserving detection of atomically replaced files, external RESETs and same-path state changes. The cached revision implements that approach, and the follow-up above confirms the expected two reads and resolves the measured overhead. Cache correctness tests were handled separately by the implementation agent; this report supplies the performance evidence. Neither timing run quantifies total evaluation duration or competition score.
