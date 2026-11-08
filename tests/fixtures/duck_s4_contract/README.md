# Duck S4 harness contract fixtures

These excerpts are from **The Duck**, the tool-using ARC-AGI-3 harness and its
TAAF adapter by **Tufa Labs**. Upstream context:
[technical write-up](https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/discussion/717133)
and [Tufa Labs article](https://tufalabs.ai/research/duck-harness/).
The excerpts retain upstream code; they are not an implementation of S10.

`manifest.json` records the original complete source-file SHA256 hashes, original
line ranges, and hashes for every retained method. `tool_agent_contract.py` and
`harness_session_contract.py` contain exact selected method source slices,
including decorators and comments, inside minimal class shells. The small
`runtime_state.py` module is copied unchanged. Fixture hashes normalize CRLF to
LF so that Git checkout settings do not affect verification.

The S10 tests execute these methods with deterministic engine and transport
substitutes. They cover the real action normalization, batching, primitive
execution, runtime serialization, compact results, and summary lifecycle. The
optional full ToolAgent/subprocess-sandbox smoke test uses a local extracted
bundle when present and explicitly skips when absent. Core regressions require
neither that bundle nor any file under `tmp/`.

To refresh from a deliberately selected upstream snapshot, place its original
`tool_agent.py`, `harness_solver.py`, and `runtime_state.py` in a source directory
and run:

```console
python tests/fixtures/duck_s4_contract/extract_fixtures.py PATH_TO_SOURCE_DIRECTORY
python -m unittest discover -s tests -p test_s10_scoped_no_impact.py -v
```

Review changes to the recorded original hashes and method slices together.
Do not manually rewrite fixture method bodies to match an S10 implementation.
