"""Measure real default-loader S10 cache over atomic same-path state changes."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import platform
import random
import shutil
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import performance_audit as base

EXPECTED_S10 = "a247847f4a4b92eefab337940a13a7070b37c4298090aea4ec2e30f91cd6e7ec"


def main():
    started = time.perf_counter()
    source = (base.ROOT / "src/s10_scoped_no_impact.py").read_bytes()
    source_hash = hashlib.sha256(source).hexdigest()
    assert source_hash == EXPECTED_S10, source_hash
    (base.OUT / "performance_s10_cached_source.py").write_bytes(source)
    s4, runtime, ensure4, source4 = base.setup()
    ensure10 = base.s10.wrap_ensure_session(ensure4)  # Default loader is essential.
    results = {"schema_version": "arc3-cached-instrumentation-v1",
               "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "python": sys.version, "platform": platform.platform(),
               "s10_source_sha256": source_hash,
               "s4_source_sha256": hashlib.sha256(source4.encode()).hexdigest(),
               "method": "Exact S4 and default-loader cached S10 wrappers; same runtime path; atomic before/after replacement; 5 outer ensures + 1 inner ensure + tool hook. File preparation outside timing; action-time atomic rename paused out of timing. Path.read_text counted without substituting snapshot loaders.",
               "cases": []}
    rng = random.Random(20260922)
    for count in (100, 500):
        before, after = base.make_state(runtime, count)
        state_path = base.OUT / f"performance_cached_active_{count}.json"
        stage_before = base.OUT / f"performance_cached_before_stage_{count}.json"
        stage_after = base.OUT / f"performance_cached_after_stage_{count}.json"
        measurements = {"s4": [], "s10_cached": []}
        counter = {"reads": 0}
        original_read_text = Path.read_text

        def counted_read(path, *args, **kwargs):
            if path == state_path:
                counter["reads"] += 1
            return original_read_text(path, *args, **kwargs)

        runner = {}
        for label, ensure in (("s4", ensure4), ("s10_cached", ensure10)):
            agent = SimpleNamespace(_session_runtime_dir=state_path.parent, _summarized_knowledge={})
            clock = {"wall": 0.0, "cpu": 0.0, "pause_wall": 0.0}

            def original_tool(self, path, arguments, *, ensure=ensure, clock=clock):
                ensure(self, path)
                # End first measurement segment before atomic state publication.
                clock["wall"] += time.perf_counter() - clock["wall_start"]
                clock["cpu"] += time.process_time() - clock["cpu_start"]
                pause = time.perf_counter()
                stage_after.replace(path)
                clock["pause_wall"] += time.perf_counter() - pause
                clock["wall_start"], clock["cpu_start"] = time.perf_counter(), time.process_time()
                self._last_step_summary = {"executed_count": 1, "executed_actions": ["UP"],
                                          "start_action_num": count + 1, "end_action_num": count + 1,
                                          "level": 1}
                return SimpleNamespace(step_executed=True)

            if label == "s4":
                hook = s4.wrap_run_python_tool(original_tool, book=s4.NoImpactBook(), load_grid=s4.duck_load_grid)
            else:
                hook = base.s10.wrap_run_python_tool(original_tool)  # No custom loader.

            def run(*, agent=agent, ensure=ensure, hook=hook, clock=clock, label=label):
                # All large file copies and initial publication happen outside timing.
                shutil.copyfile(before, stage_before)
                stage_before.replace(state_path)
                shutil.copyfile(after, stage_after)
                counter["reads"] = 0
                clock.update(wall=0.0, cpu=0.0, pause_wall=0.0)
                with patch.object(Path, "read_text", counted_read):
                    clock["wall_start"], clock["cpu_start"] = time.perf_counter(), time.process_time()
                    for _ in range(4):
                        ensure(agent, state_path)
                    hook(agent, state_path, {})
                    ensure(agent, state_path)
                    clock["wall"] += time.perf_counter() - clock["wall_start"]
                    clock["cpu"] += time.process_time() - clock["cpu_start"]
                assert counter["reads"] == 2, (label, counter)
                if label == "s10_cached":
                    memory = base.s10.memory_for(agent)
                    assert memory.paths[str(state_path.resolve())]["snapshot"]["step"] == count + 1
                return {"wall_ms": clock["wall"] * 1000, "cpu_ms": clock["cpu"] * 1000,
                        "reads": counter["reads"], "excluded_atomic_replace_ms": clock["pause_wall"] * 1000}

            runner[label] = run

        # Warm both paths once; redirect the repeated S4 confirmation console line
        # equally for every subsequent measurement, retaining the print operation.
        with contextlib.redirect_stdout(io.StringIO()):
            for run in runner.values():
                run()
            for _ in range(5):
                order = list(runner)
                rng.shuffle(order)
                for label in order:
                    measurements[label].append(runner[label]())

        cache_agent = SimpleNamespace(_session_runtime_dir=state_path.parent)
        ensure10(cache_agent, state_path)
        hit_times = []
        counter["reads"] = 0
        with patch.object(Path, "read_text", counted_read):
            for _ in range(11):
                t = time.perf_counter()
                ensure10(cache_agent, state_path)
                hit_times.append((time.perf_counter() - t) * 1000)
        assert counter["reads"] == 0, counter
        case = {"history_entries": count, "file_bytes": before.stat().st_size, "repeats": 5,
                "cache_hit_ensure_median_ms": statistics.median(hit_times),
                "cache_hit_ensure_reads_for_11_calls": counter["reads"],
                "profiles": {label: {"median_wall_ms": statistics.median(s["wall_ms"] for s in samples),
                                     "median_cpu_ms": statistics.median(s["cpu_ms"] for s in samples),
                                     "samples": samples}
                             for label, samples in measurements.items()}}
        a, b = (case["profiles"][label]["median_wall_ms"] for label in ("s4", "s10_cached"))
        case.update(delta_ms=b - a, candidate_over_baseline=b / a)
        results["cases"].append(case)
        print(json.dumps({"history": count, "s4_ms": a, "s10_cached_ms": b,
                          "delta_ms": b - a, "ratio": b / a,
                          "reads_each": 2, "cache_hit_ensure_ms": case["cache_hit_ensure_median_ms"]}), flush=True)
    results["elapsed_s"] = time.perf_counter() - started
    results["s10_counters"] = dict(base.s10._COUNTERS)
    assert results["s10_counters"]["internal_errors"] == 0
    (base.OUT / "performance_results_cached.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
