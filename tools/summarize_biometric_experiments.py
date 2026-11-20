"""Summarize recognition and active-liveness experiment CSV results."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import resolve_project_path  # noqa: E402


DEFAULT_INPUT = Path("storage/evaluation/active_experiments/attempts.csv")
DEFAULT_JSON = Path("storage/evaluation/active_experiments/summary.json")
DEFAULT_MARKDOWN = Path("storage/evaluation/active_experiments/summary.md")
UNKNOWN_IDENTITY = "UNKNOWN"
WILSON_Z_95 = 1.959963984540054


def _as_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "pass", "accepted"}


def _as_float(value: str | None) -> float | None:
    try:
        parsed = float((value or "").strip())
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _normalize_reason(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _is_liveness_fta(row: dict[str, str]) -> bool:
    """Return True when no evaluable face trial was acquired.

    Older experiment rows may be marked ``usable`` even though the recorded
    failure reason states that no face was detected. Those rows are retained as
    raw evidence but must not be counted as successful attack rejections.
    """

    reasons = (
        _normalize_reason(row.get("failure_reason")),
        _normalize_reason(row.get("liveness_failure_reason")),
    )
    return (
        row.get("acquisition_result") != "usable"
        or any(reason.startswith("no face detected") for reason in reasons)
    )


def wilson_interval(successes: int, total: int) -> tuple[float, float] | None:
    """Return a two-sided 95% Wilson score interval for a binomial proportion."""

    if total <= 0:
        return None
    proportion = successes / total
    z_squared = WILSON_Z_95**2
    denominator = 1.0 + z_squared / total
    centre = (proportion + z_squared / (2.0 * total)) / denominator
    spread = (
        WILSON_Z_95
        * math.sqrt(
            (proportion * (1.0 - proportion) / total)
            + (z_squared / (4.0 * total**2))
        )
        / denominator
    )
    return max(0.0, centre - spread), min(1.0, centre + spread)


def _rate(successes: int, total: int) -> dict[str, object]:
    interval = wilson_interval(successes, total)
    return {
        "count": successes,
        "total": total,
        "rate": successes / total if total else None,
        "wilson_95_ci": list(interval) if interval is not None else None,
    }


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _latency(rows: Iterable[dict[str, str]], field: str) -> dict[str, float | int | None]:
    values = [value for row in rows if (value := _as_float(row.get(field))) is not None]
    return {
        "count": len(values),
        "mean_ms": statistics.fmean(values) if values else None,
        "median_ms": statistics.median(values) if values else None,
        "q1_ms": _percentile(values, 0.25),
        "q3_ms": _percentile(values, 0.75),
        "p95_ms": _percentile(values, 0.95),
    }


def _recognition_group(rows: list[dict[str, str]]) -> dict[str, object]:
    usable = [row for row in rows if row.get("acquisition_result") == "usable"]
    enrolled = [
        row
        for row in usable
        if row.get("enrollment_status") == "enrolled"
        and row.get("expected_identity", "").upper() != UNKNOWN_IDENTITY
    ]
    unknown = [
        row
        for row in usable
        if row.get("enrollment_status") == "unknown"
        or row.get("expected_identity", "").upper() == UNKNOWN_IDENTITY
    ]
    true_accepts = sum(row.get("outcome") == "TRUE_ACCEPT" for row in enrolled)
    misidentifications = sum(row.get("outcome") == "MISIDENTIFICATION" for row in enrolled)
    false_rejects = len(enrolled) - true_accepts
    false_accepts = sum(_as_bool(row.get("accepted")) for row in unknown)
    true_rejects = len(unknown) - false_accepts
    correct_decisions = true_accepts + true_rejects
    decision_total = len(enrolled) + len(unknown)
    return {
        "attempts_total": len(rows),
        "usable_attempts": len(usable),
        "failure_to_acquire": _rate(len(rows) - len(usable), len(rows)),
        "enrolled_genuine_attempts": len(enrolled),
        "unknown_attempts": len(unknown),
        "true_accepts": true_accepts,
        "false_rejects": false_rejects,
        "true_rejects": true_rejects,
        "false_accepts": false_accepts,
        "misidentifications": misidentifications,
        "tar": _rate(true_accepts, len(enrolled)),
        "frr": _rate(false_rejects, len(enrolled)),
        "tnr": _rate(true_rejects, len(unknown)),
        "far": _rate(false_accepts, len(unknown)),
        "correct_identification_rate": _rate(true_accepts, len(enrolled)),
        "overall_decision_accuracy": _rate(correct_decisions, decision_total),
        "recognition_processing_latency": _latency(usable, "processing_ms"),
    }


def _liveness_group(rows: list[dict[str, str]]) -> dict[str, object]:
    evaluable = [row for row in rows if not _is_liveness_fta(row)]
    passed = sum(_as_bool(row.get("liveness_pass")) for row in evaluable)
    rejected = len(evaluable) - passed
    expected_accept = [row for row in evaluable if row.get("expected_decision") == "accept"]
    expected_reject = [row for row in evaluable if row.get("expected_decision") == "reject"]
    live_successes = sum(_as_bool(row.get("liveness_pass")) for row in expected_accept)
    attack_rejections = sum(not _as_bool(row.get("liveness_pass")) for row in expected_reject)
    correct_decisions = live_successes + attack_rejections
    return {
        "attempts_total": len(rows),
        "usable_attempts": len(evaluable),
        "evaluable_attempts": len(evaluable),
        "failure_to_acquire": _rate(len(rows) - len(evaluable), len(rows)),
        "passes": passed,
        "rejections": rejected,
        "pass_rate": _rate(passed, len(evaluable)),
        "liveness_success_rate": _rate(live_successes, len(expected_accept)),
        "challenge_failure_rate": _rate(len(expected_accept) - live_successes, len(expected_accept)),
        "attack_rejection_rate": _rate(attack_rejections, len(expected_reject)),
        "unexpected_attack_acceptance_rate": _rate(
            len(expected_reject) - attack_rejections,
            len(expected_reject),
        ),
        "correct_decision_rate": _rate(correct_decisions, len(evaluable)),
        "validation_processing_latency": _latency(evaluable, "processing_ms"),
        "capture_plus_validation_latency": _latency(evaluable, "total_ms"),
    }


def summarize(rows: list[dict[str, str]]) -> dict[str, object]:
    """Produce overall and stratified summaries from attempt-level records."""

    recognition = [row for row in rows if row.get("mode") == "recognition"]
    liveness = [row for row in rows if row.get("mode") == "liveness"]
    recognition_conditions = sorted({row.get("condition", "") for row in recognition if row.get("condition")})
    liveness_scenarios = sorted({row.get("scenario", "") for row in liveness if row.get("scenario")})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "attempt_rows": len(rows),
        "unique_attempt_ids": len({row.get("attempt_id") for row in rows if row.get("attempt_id")}),
        "recognition": {
            "overall": _recognition_group(recognition),
            "by_condition": {
                condition: _recognition_group(
                    [row for row in recognition if row.get("condition") == condition]
                )
                for condition in recognition_conditions
            },
        },
        "active_liveness": {
            "overall": _liveness_group(liveness),
            "by_scenario": {
                scenario: _liveness_group(
                    [row for row in liveness if row.get("scenario") == scenario]
                )
                for scenario in liveness_scenarios
            },
        },
    }


def _percent(value: object) -> str:
    if not isinstance(value, (float, int)):
        return "N/A"
    return f"{float(value) * 100.0:.2f}%"


def _metric_text(metric: dict[str, object]) -> str:
    interval = metric.get("wilson_95_ci")
    if isinstance(interval, list) and len(interval) == 2:
        ci = f"{_percent(interval[0])}-{_percent(interval[1])}"
    else:
        ci = "N/A"
    return f"{metric.get('count', 0)}/{metric.get('total', 0)} | {_percent(metric.get('rate'))} | {ci}"


def _markdown(summary: dict[str, object]) -> str:
    recognition = summary["recognition"]
    active_liveness = summary["active_liveness"]
    rec_overall = recognition["overall"]
    live_overall = active_liveness["overall"]
    lines = [
        "# Biometric Experiment Summary",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "## Recognition",
        "",
        "| Metric | Count / total | Rate | 95% Wilson CI |",
        "|---|---:|---:|---:|",
    ]
    for label, key in (
        ("True accept rate", "tar"),
        ("False reject rate", "frr"),
        ("True reject rate", "tnr"),
        ("False accept rate", "far"),
        ("Overall decision accuracy", "overall_decision_accuracy"),
        ("Failure to acquire", "failure_to_acquire"),
    ):
        metric = rec_overall[key]
        interval = metric.get("wilson_95_ci")
        ci = (
            f"{_percent(interval[0])}-{_percent(interval[1])}"
            if isinstance(interval, list) and len(interval) == 2
            else "N/A"
        )
        lines.append(
            f"| {label} | {metric['count']} / {metric['total']} | {_percent(metric['rate'])} | {ci} |"
        )
    latency = rec_overall["recognition_processing_latency"]
    lines.extend(
        [
            "",
            f"Recognition latency: mean={latency['mean_ms'] or 0:.2f} ms, "
            f"median={latency['median_ms'] or 0:.2f} ms, P95={latency['p95_ms'] or 0:.2f} ms.",
            "",
            "### Recognition by condition",
            "",
            "| Condition | Usable | TAR | FRR | FAR | FTA |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for condition, metrics in recognition["by_condition"].items():
        lines.append(
            f"| {condition} | {metrics['usable_attempts']} | {_percent(metrics['tar']['rate'])} | "
            f"{_percent(metrics['frr']['rate'])} | {_percent(metrics['far']['rate'])} | "
            f"{_percent(metrics['failure_to_acquire']['rate'])} |"
        )

    lines.extend(
        [
            "",
            "## Active head-turn liveness",
            "",
            f"Submissions: {live_overall['attempts_total']}; evaluable trials: {live_overall['evaluable_attempts']}; "
            f"failure to acquire: {_metric_text(live_overall['failure_to_acquire'])}.",
            "",
            "| Scenario | Evaluable trials | Pass | Reject | Target rate | 95% Wilson CI |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for scenario, metrics in active_liveness["by_scenario"].items():
        target = (
            metrics["liveness_success_rate"]
            if scenario == "correct"
            else metrics["attack_rejection_rate"]
        )
        interval = target.get("wilson_95_ci")
        ci = (
            f"{_percent(interval[0])}-{_percent(interval[1])}"
            if isinstance(interval, list) and len(interval) == 2
            else "N/A"
        )
        lines.append(
            f"| {scenario} | {metrics['usable_attempts']} | {metrics['passes']} | "
            f"{metrics['rejections']} | {_percent(target['rate'])} | {ci} |"
        )
    live_latency = live_overall["validation_processing_latency"]
    lines.extend(
        [
            "",
            f"Active-liveness validation latency: mean={live_latency['mean_ms'] or 0:.2f} ms, "
            f"median={live_latency['median_ms'] or 0:.2f} ms, P95={live_latency['p95_ms'] or 0:.2f} ms.",
            "",
            "Rates with zero denominators are reported as N/A. Acquisition failures are reported separately.",
            "",
        ]
    )
    return "\n".join(lines)


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Experiment CSV does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Experiment CSV contains no attempt rows.")
    required = {"attempt_id", "mode", "acquisition_result", "outcome"}
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"Experiment CSV is missing columns: {', '.join(sorted(missing))}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    input_path = resolve_project_path(args.input)
    json_path = resolve_project_path(args.json)
    markdown_path = resolve_project_path(args.markdown)
    rows = _read_rows(input_path)
    result = summarize(rows)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(_markdown(result), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nJSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
