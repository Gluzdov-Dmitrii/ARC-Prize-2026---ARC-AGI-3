"""Strict, stdlib-only exports and matched-game comparisons of TAAF scores.

Scores come directly from GameRun.final_score; they are never re-scored or
rescaled. This module can also be embedded in a notebook cell without TAAF or
project imports. Export each pass separately: one record per expected game.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "arc3-sprint-run-v1"
COMPARISON_SCHEMA_VERSION = "arc3-sprint-paired-v1"
SCORE_SCALE = "framework-native"
SCORE_SOURCE = "taaf.GameRun.final_score"
FINAL_STATES = frozenset({"won", "gave_up", "cancelled"})
COMPARABLE_MODES = frozenset({"panel", "public25"})


def _number(value: Any, label: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (nonnegative and result < 0):
        raise ValueError(f"{label} must be finite" + (" and nonnegative" if nonnegative else ""))
    return result


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _ids(values: Any, label: str) -> list[str]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError(f"{label} must be a nonempty list of game IDs")
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError(f"{label} contains an invalid game ID")
    if len(set(values)) != len(values):
        raise ValueError(f"{label} contains duplicate game IDs")
    return list(values)


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, allow_nan=False, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Config must contain finite JSON values: {exc}") from exc


def _records_by_id(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    expected = _ids(summary.get("expected_game_ids"), "expected_game_ids")
    records = summary.get("games")
    if not isinstance(records, list):
        raise ValueError("games must be a list")
    result = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Each game record must be an object")
        game_id = record.get("game_id")
        if not isinstance(game_id, str) or not game_id.strip():
            raise ValueError("Missing game_id")
        if game_id in result:
            raise ValueError(f"Duplicate game record: {game_id}")
        if record.get("state") not in FINAL_STATES:
            raise ValueError(f"{game_id}: invalid final state {record.get('state')!r}")
        _number(record.get("final_score"), f"{game_id}.final_score")
        total = _integer(record.get("total_levels"), f"{game_id}.total_levels", minimum=1)
        completed = _integer(record.get("levels_completed"), f"{game_id}.levels_completed")
        if completed > total:
            raise ValueError(f"{game_id}: levels_completed exceeds total_levels")
        if record.get("state") == "won" and completed != total:
            raise ValueError(f"{game_id}: won state requires all levels completed")
        _integer(record.get("action_count"), f"{game_id}.action_count")
        _number(record.get("runtime_s"), f"{game_id}.runtime_s", nonnegative=True)
        if not isinstance(record.get("baselines_available"), bool):
            raise ValueError(f"{game_id}: baselines_available must be a boolean")
        result[game_id] = record
    missing = sorted(set(expected) - result.keys())
    extra = sorted(result.keys() - set(expected))
    if missing or extra:
        raise ValueError(f"Game coverage mismatch: missing={missing}, unexpected={extra}")
    return result


def build_run_summary(
    bm: Any,
    profile: str,
    mode: str,
    expected_game_ids: list[str],
    elapsed_s: float,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Export one ended TAAF Benchmark pass, or raise ValueError on invalid data.

    Cancelled runs with framework-finalized scores remain in the sample.
    Hidden-baseline and smoke results may be exported but cannot be compared as
    quality evidence. Config should contain model, seed, budgets, and all other
    shared evaluation controls; profile identifies the deliberate treatment.
    """
    expected = _ids(expected_game_ids, "expected_game_ids")
    if not isinstance(profile, str) or not profile.strip():
        raise ValueError("profile must be a nonempty string")
    if not isinstance(mode, str) or not mode.strip():
        raise ValueError("mode must be a nonempty string")
    if getattr(bm, "n_passes", None) != 1:
        raise ValueError("Export exactly one pass per summary (n_passes must equal 1)")
    if getattr(bm, "end_time", None) is None:
        raise ValueError("Benchmark has not ended")
    if config is not None and not isinstance(config, dict):
        raise ValueError("config must be a dict or None")
    games = []
    for run in bm.game_runs:
        actions = list(run.actions_per_level)
        if len(actions) != run.number_of_levels:
            raise ValueError(f"{run.game_id}: actions_per_level length mismatch")
        for count in actions:
            _integer(count, f"{run.game_id}.actions_per_level")
        action_count = len(run.history)
        if sum(actions) != action_count:
            raise ValueError(f"{run.game_id}: action history and level counters disagree")
        games.append({
            "game_id": run.game_id,
            "state": run.state,
            "final_score": _number(run.final_score, f"{run.game_id}.final_score"),
            "levels_completed": run.levels_completed,
            "total_levels": run.number_of_levels,
            "action_count": action_count,
            "runtime_s": _number(run.final_wallclock_seconds, f"{run.game_id}.runtime_s", nonnegative=True),
            "baselines_available": run.base_actions_per_level is not None,
        })
    summary = {
        "schema_version": SCHEMA_VERSION,
        "profile": profile,
        "mode": mode,
        "score_source": SCORE_SOURCE,
        "score_scale": SCORE_SCALE,
        "expected_game_ids": expected,
        "n_passes": 1,
        "elapsed_s": _number(elapsed_s, "elapsed_s", nonnegative=True),
        "config": _json_copy(config or {}),
        "games": games,
    }
    indexed = _records_by_id(summary)
    summary["games"] = [indexed[game_id] for game_id in expected]
    summary["valid"] = True
    summary["mean_score"] = statistics.fmean(record["final_score"] for record in games)
    summary["quality_comparison_eligible"] = (
        mode in COMPARABLE_MODES and all(record["baselines_available"] for record in games)
    )
    summary["interpretation"] = (
        "Framework-native scores for these games only. Smoke and competition runs "
        "are operational checks, not quality evidence; hidden baselines make local "
        "scores unsuitable for quality comparisons."
    )
    return summary


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(destination)


def write_run_summary(
    bm: Any,
    output_path: str | Path,
    *,
    profile: str,
    mode: str,
    expected_game_ids: list[str],
    elapsed_s: float,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate, atomically write a UTF-8 JSON summary, and return its contents."""
    summary = build_run_summary(bm, profile, mode, expected_game_ids, elapsed_s, config)
    _write_json(output_path, summary)
    return summary


def _comparison_config(summary: dict[str, Any]) -> dict[str, Any]:
    config = summary.get("config")
    if not isinstance(config, dict):
        raise ValueError("Comparison requires a config object")
    if any(key not in config for key in ("model", "seed", "budgets")):
        raise ValueError("Comparison requires config.model, config.seed, and config.budgets")
    if not isinstance(config["model"], str) or not config["model"].strip():
        raise ValueError("Comparison requires a nonempty model reference")
    if config["seed"] is not None:
        _integer(config["seed"], "config.seed", minimum=-1)
    if not isinstance(config["budgets"], dict) or not config["budgets"]:
        raise ValueError("Comparison requires nonempty config.budgets")
    return _json_copy(config)


def _quantile(sorted_values: list[float], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    return sorted_values[lower] + (position - lower) * (sorted_values[upper] - sorted_values[lower])


def compare_summaries(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    bootstrap_samples: int = 10000,
    bootstrap_seed: int = 0,
) -> dict[str, Any]:
    """Compare matched games under identical recorded evaluation controls.

    Bootstrap resamples game pairs, not levels or individual actions. The CI is
    descriptive of the selected sample and does not establish generalization.
    """
    _integer(bootstrap_samples, "bootstrap_samples", minimum=1)
    _integer(bootstrap_seed, "bootstrap_seed")
    indexed = []
    for label, summary in (("baseline", baseline), ("candidate", candidate)):
        if not isinstance(summary, dict) or summary.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"{label}: unsupported summary schema")
        if summary.get("valid") is not True or summary.get("n_passes") != 1:
            raise ValueError(f"{label}: summary must be valid and single-pass")
        if summary.get("mode") not in COMPARABLE_MODES:
            raise ValueError(f"{label}: smoke/competition or unknown mode cannot be quality evidence")
        if summary.get("score_source") != SCORE_SOURCE or summary.get("score_scale") != SCORE_SCALE:
            raise ValueError(f"{label}: score source or scale mismatch")
        _number(summary.get("elapsed_s"), f"{label}.elapsed_s", nonnegative=True)
        records = _records_by_id(summary)
        if any(not record["baselines_available"] for record in records.values()):
            raise ValueError(f"{label}: hidden baselines cannot support a quality comparison")
        indexed.append(records)
    if baseline["mode"] != candidate["mode"]:
        raise ValueError("Evaluation mode mismatch")
    if indexed[0].keys() != indexed[1].keys():
        raise ValueError("Baseline and candidate game IDs differ")
    base_config, candidate_config = _comparison_config(baseline), _comparison_config(candidate)
    if base_config != candidate_config:
        changed = sorted(key for key in base_config.keys() | candidate_config.keys()
                         if key not in base_config or key not in candidate_config or base_config[key] != candidate_config[key])
        raise ValueError(f"Evaluation config mismatch: {changed}")
    per_game = []
    for game_id in sorted(indexed[0]):
        first, second = indexed[0][game_id], indexed[1][game_id]
        if first["total_levels"] != second["total_levels"]:
            raise ValueError(f"{game_id}: total_levels mismatch")
        per_game.append({
            "game_id": game_id,
            "baseline_score": first["final_score"],
            "candidate_score": second["final_score"],
            "delta": second["final_score"] - first["final_score"],
        })
    deltas = [record["delta"] for record in per_game]
    rng = random.Random(bootstrap_seed)
    means = sorted(statistics.fmean(rng.choices(deltas, k=len(deltas))) for _ in range(bootstrap_samples))
    stochastic = base_config["seed"] in (None, -1)
    warnings = [
        "Descriptive matched-game comparison; no claim of statistical significance or hidden-test generalization.",
        "The bootstrap assumes sampled games are independent; related/public games may violate this assumption.",
        "One run per profile does not estimate within-game run-to-run variability.",
    ]
    if len(deltas) < 30:
        warnings.append("Small selected sample: the interval may be unstable or degenerate; repeat across seeds and broader panels.")
    if stochastic:
        warnings.append("Stochastic unpaired sampling: game IDs are matched, but seed=None/-1 does not pair model RNG draws.")
    else:
        warnings.append("Equal recorded seeds do not by themselves guarantee identical model RNG draws or deterministic serving.")
    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "baseline_profile": baseline.get("profile"),
        "candidate_profile": candidate.get("profile"),
        "mode": baseline["mode"],
        "score_scale": SCORE_SCALE,
        "config": base_config,
        "sample_size": len(deltas),
        "pairing": "game_id; stochastic unpaired sampling" if stochastic else "game_id; equal recorded seed",
        "baseline_mean": statistics.fmean(record["baseline_score"] for record in per_game),
        "candidate_mean": statistics.fmean(record["candidate_score"] for record in per_game),
        "mean_delta": statistics.fmean(deltas),
        "wins": sum(delta > 0 for delta in deltas),
        "ties": sum(delta == 0 for delta in deltas),
        "losses": sum(delta < 0 for delta in deltas),
        "paired_bootstrap_ci": {
            "confidence": 0.95,
            "lower": _quantile(means, 0.025),
            "upper": _quantile(means, 0.975),
            "samples": bootstrap_samples,
            "seed": bootstrap_seed,
            "resampling_unit": "game pair",
            "method": "percentile with linear quantile interpolation",
        },
        "games": per_game,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8-sig"))
        candidate = json.loads(args.candidate.read_text(encoding="utf-8-sig"))
        comparison = compare_summaries(baseline, candidate, bootstrap_samples=args.bootstrap_samples,
                                       bootstrap_seed=args.bootstrap_seed)
        if args.output:
            _write_json(args.output, comparison)
        print(json.dumps(comparison, indent=2, allow_nan=False))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    return 0


# Notebook cells have __name__ == '__main__' but no __file__.
if __name__ == "__main__" and "__file__" in globals():
    raise SystemExit(main())
