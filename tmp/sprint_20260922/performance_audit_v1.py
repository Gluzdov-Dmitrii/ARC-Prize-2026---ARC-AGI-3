"""Bounded local S4/S10 instrumentation microbenchmark; no model or GPU work."""
from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
import platform
import random
import statistics
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tmp/sprint_20260922"
sys.path.insert(0, str(ROOT))
from src import s10_scoped_no_impact as s10

PARENT = ROOT / "tmp/kernels/s4-no-impact/duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
RUNTIME = ROOT / "tmp/src/duck-harness/ARC3-Inference/inference/agent/runtime_state.py"
AGENT = ROOT / "tmp/src/duck-harness/ARC3-Inference/inference/agent/tool_agent.py"


def setup():
    notebook = json.loads(PARENT.read_text(encoding="utf-8"))
    cell = "".join(notebook["cells"][13]["source"])
    source = next(node.value.value for node in ast.parse(cell).body
                  if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "S4_SOURCE" for target in node.targets))
    s4 = ModuleType("performance_s4")
    sys.modules[s4.__name__] = s4
    exec(compile(source, str(PARENT) + ":S4_SOURCE", "exec"), s4.__dict__)
    runtime = ModuleType("performance_runtime")
    sys.modules[runtime.__name__] = runtime
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.ImportFrom) and (node.module or "").startswith("inference"))]
    runtime.format_grid_ascii = lambda grid: "unused in this benchmark"
    exec(compile(tree, str(RUNTIME), "exec"), runtime.__dict__)
    # S4's exact duck_load_grid import resolves the actual runtime loader here.
    inference, package, ta = (ModuleType(name) for name in ("inference", "inference.agent", "inference.agent.tool_agent"))
    ta.load_runtime_state = runtime.load_runtime_state
    package.tool_agent, inference.agent = ta, package
    for module in (inference, package, ta):
        sys.modules[module.__name__] = module
    agent_tree = ast.parse(AGENT.read_text(encoding="utf-8"))
    agent_class = next(node for node in agent_tree.body if isinstance(node, ast.ClassDef) and node.name == "ToolAgent")
    ensure = next(node for node in agent_class.body if isinstance(node, ast.FunctionDef) and node.name == "_ensure_session")
    ensure_module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), ensure], type_ignores=[])
    namespace = {"_empty_world_model": lambda: {}}
    exec(compile(ast.fix_missing_locations(ensure_module), str(AGENT), "exec"), namespace)
    return s4, runtime, namespace["_ensure_session"], source


def make_state(runtime, count):
    grid = tuple(tuple((row * 3 + col * 5) % 16 for col in range(64)) for row in range(64))
    entries = [runtime.HistoryEntry(action="RESET" if i % 79 == 0 else "UP",
                                  frame=runtime.Frame(grid=grid, step=i + 1, level=1))
               for i in range(count)]
    before = OUT / f"performance_state_{count}_before.json"
    after = OUT / f"performance_state_{count}_after.json"
    runtime.write_runtime_state(before, current_frame=entries[-1].frame, history=entries)
    entries.append(runtime.HistoryEntry(action="UP", frame=runtime.Frame(grid=grid, step=count + 1, level=1)))
    runtime.write_runtime_state(after, current_frame=entries[-1].frame, history=entries)
    return before, after


def callables(s4, original_ensure, before, after, count):
    ensure10 = s10.wrap_ensure_session(original_ensure)
    agent4 = SimpleNamespace(_session_runtime_dir=before.parent, _summarized_knowledge={})
    agent10 = SimpleNamespace(_session_runtime_dir=before.parent)

    def original_tool(agent, state_path, arguments):
        # The actual inner ensure call is common to S4/S10. S10 in_tool skips its read.
        (ensure10 if agent is agent10 else original_ensure)(agent, state_path)
        agent._last_step_summary = {"executed_count": 1, "executed_actions": ["UP"],
                                   "start_action_num": count + 1, "end_action_num": count + 1,
                                   "level": 1}
        return SimpleNamespace(step_executed=True)

    def alternating(loader):
        calls = 0
        def load(_):
            nonlocal calls
            path = before if calls % 2 == 0 else after
            calls += 1
            return loader(path)
        return load

    hook4 = s4.wrap_run_python_tool(original_tool, book=s4.NoImpactBook(), load_grid=alternating(s4.duck_load_grid))
    hook10 = s10.wrap_run_python_tool(original_tool, loader=alternating(s10.load_snapshot))

    def cycle4():
        for _ in range(4):
            original_ensure(agent4, before)
        hook4(agent4, before, {})
        original_ensure(agent4, before)

    def cycle10():
        for _ in range(4):
            ensure10(agent10, before)
        hook10(agent10, before, {})
        ensure10(agent10, after)

    return {
        "s4_load_grid": lambda: s4.duck_load_grid(before),
        "s10_load_snapshot": lambda: s10.load_snapshot(before),
        "s4_ensure_session": lambda: original_ensure(agent4, before),
        "s10_ensure_session": lambda: ensure10(agent10, before),
        "s4_tool_hook": lambda: hook4(agent4, before, {}),
        "s10_tool_hook": lambda: hook10(agent10, before, {}),
        "s4_single_request_instrumentation": cycle4,
        "s10_single_request_instrumentation": cycle10,
    }


def summarize(samples):
    return {"median_wall_ms": statistics.median(item[0] for item in samples),
            "min_wall_ms": min(item[0] for item in samples),
            "max_wall_ms": max(item[0] for item in samples),
            "median_cpu_ms": statistics.median(item[1] for item in samples),
            "wall_samples_ms": [item[0] for item in samples]}


def main():
    started = time.perf_counter()
    s4, runtime, ensure, source = setup()
    report = {
        "schema_version": "arc3-instrumentation-microbenchmark-v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version, "platform": platform.platform(),
        "source_sha256": {"parent_s4_embedded_source": hashlib.sha256(source.encode()).hexdigest(),
                          "runtime_state": hashlib.sha256(RUNTIME.read_bytes()).hexdigest(),
                          "tool_agent": hashlib.sha256(AGENT.read_bytes()).hexdigest(),
                          "s10": hashlib.sha256((ROOT / "src/s10_scoped_no_impact.py").read_bytes()).hexdigest()},
        "method": {"grid_size": [64, 64], "writer": "exact runtime.write_runtime_state (indent=2)",
                   "cache": "warm OS cache; all operations warmed once; serial randomized operation order",
                   "single_request_extra_ensures": 5,
                   "single_request_call_sites": ["analyze entry", "initial _tools for trim", "request-loop _tools", "_dispatch_tool", "finally _tools for persistent history"],
                   "single_request_snapshot_reads": {"S4": 2, "S10": 7},
                   "cpu_timer": "time.process_time", "wall_timer": "time.perf_counter",
                   "stubs": "Tool body returns fresh one-action summary; original ensure is AST-extracted unchanged. S4 duck_load_grid uses exact runtime loader via import shim. Only unused grid ASCII rendering import stubbed."},
        "cases": [],
        "limitations": ["Synthetic schema-faithful states, not recorded game trajectories.",
                        "Windows local warm-cache CPU/I/O instrumentation only; not Kaggle or GPU/LLM latency.",
                        "Base harness JSON reads, prompt building, model serving, actions, and state writes excluded from timed region.",
                        "Single-request estimate follows source call sites with one Python tool and persistent history; extra requests/tools change counts.",
                        "Repeated synthetic transition causes S10 step rollback reset between iterations; this audit is not a memory-policy quality test.",
                        "Small timing samples and current host background load limit precision."]}
    rng = random.Random(20260922)
    for count, repeats in ((10, 11), (100, 7), (500, 5)):
        before, after = make_state(runtime, count)
        functions = callables(s4, ensure, before, after, count)
        assert s4.duck_load_grid(before) == s10.load_snapshot(before)["grid"]
        assert len(runtime.load_runtime_state(before)[1]) == count
        with contextlib.redirect_stdout(io.StringIO()):
            for function in functions.values():
                function()
        samples = {name: [] for name in functions}
        for _ in range(repeats):
            names = list(functions)
            rng.shuffle(names)
            for name in names:
                wall, cpu = time.perf_counter(), time.process_time()
                functions[name]()
                samples[name].append(((time.perf_counter() - wall) * 1000,
                                      (time.process_time() - cpu) * 1000))
        case = {"history_entries": count, "before_file_bytes": before.stat().st_size,
                "after_file_bytes": after.stat().st_size, "repeats": repeats,
                "operations": {name: summarize(values) for name, values in samples.items()}}
        for group, baseline, candidate in (("loader", "s4_load_grid", "s10_load_snapshot"),
                                           ("tool_hook", "s4_tool_hook", "s10_tool_hook"),
                                           ("single_request", "s4_single_request_instrumentation", "s10_single_request_instrumentation")):
            base = case["operations"][baseline]["median_wall_ms"]
            cand = case["operations"][candidate]["median_wall_ms"]
            case[group + "_comparison"] = {"delta_ms": cand - base, "candidate_over_baseline": cand / base}
        report["cases"].append(case)
        print(json.dumps({"history": count, "size_mb": before.stat().st_size / 1e6,
                          "single_request": case["single_request_comparison"],
                          "operations_ms": {key: round(value["median_wall_ms"], 3) for key, value in case["operations"].items()}}), flush=True)
        if time.perf_counter() - started > 120:
            report["bounded_stop"] = "120-second budget reached after completed case"
            break
    report["elapsed_s"] = time.perf_counter() - started
    report["s10_counters"] = dict(s10._COUNTERS)
    (OUT / "performance_results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
