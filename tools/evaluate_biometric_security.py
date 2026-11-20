"""Local-only recognition and presentation-attack evaluation utility."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings, resolve_project_path  # noqa: E402
from app.domain.services.liveness_service import LivenessFrame  # noqa: E402
from app.infrastructure.face_ai.face_alignment import (  # noqa: E402
    ALIGNED_PREPROCESSING_VERSION,
    LEGACY_PREPROCESSING_VERSION,
    align_face,
)
from app.infrastructure.face_ai.face_anti_spoofing import (  # noqa: E402
    OnnxFaceAntiSpoofingService,
    _sha384,
)
from app.infrastructure.face_ai.facenet_embedder import FaceNetEmbedder  # noqa: E402
from app.infrastructure.face_ai.mtcnn_face_detector import MTCNNFaceDetector  # noqa: E402
from app.infrastructure.face_ai.recognition_policy import (  # noqa: E402
    SUPPORTED_AGGREGATIONS,
    aggregate_similarity,
)


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
MIN_PAD_CALIBRATION_ATTEMPTS_PER_CLASS = 10


@dataclass(frozen=True)
class BinaryMetrics:
    threshold: float
    false_accept_rate: float
    false_reject_rate: float
    true_accept_rate: float
    true_reject_rate: float
    eer: float


def _normalized(vector: list[float]) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    if norm <= 0.0 or not np.isfinite(array).all():
        raise ValueError("An embedding could not be normalized.")
    return array / norm


def _operating_points(genuine: list[float], impostor: list[float]) -> list[BinaryMetrics]:
    if not genuine or not impostor:
        raise ValueError("Both genuine and impostor scores are required.")
    values = sorted(set(genuine + impostor))
    thresholds = [values[0] - 1e-6]
    thresholds.extend((left + right) / 2.0 for left, right in zip(values, values[1:]))
    thresholds.append(values[-1] + 1e-6)
    points: list[BinaryMetrics] = []
    for threshold in thresholds:
        false_accepts = sum(score >= threshold for score in impostor)
        false_rejects = sum(score < threshold for score in genuine)
        far = false_accepts / len(impostor)
        frr = false_rejects / len(genuine)
        points.append(
            BinaryMetrics(
                threshold=threshold,
                false_accept_rate=far,
                false_reject_rate=frr,
                true_accept_rate=1.0 - frr,
                true_reject_rate=1.0 - far,
                eer=(far + frr) / 2.0,
            )
        )
    return points


def _eer_point(genuine: list[float], impostor: list[float]) -> BinaryMetrics:
    points = _operating_points(genuine, impostor)
    return min(
        points,
        key=lambda item: (
            abs(item.false_accept_rate - item.false_reject_rate),
            item.eer,
            item.false_accept_rate,
            -item.threshold,
        ),
    )


def _metrics_at_threshold(
    genuine: list[float],
    impostor: list[float],
    threshold: float,
) -> BinaryMetrics:
    far = sum(score >= threshold for score in impostor) / len(impostor)
    frr = sum(score < threshold for score in genuine) / len(genuine)
    return BinaryMetrics(
        threshold=threshold,
        false_accept_rate=far,
        false_reject_rate=frr,
        true_accept_rate=1.0 - frr,
        true_reject_rate=1.0 - far,
        eer=(far + frr) / 2.0,
    )


def _image_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def evaluate_recognition(root: Path, *, preprocessing: str, top_k: int) -> dict[str, object]:
    identities = {
        directory.name: _image_files(directory)
        for directory in sorted(root.iterdir())
        if directory.is_dir()
    }
    identities = {key: files for key, files in identities.items() if len(files) >= 2}
    if len(identities) < 2:
        raise ValueError("Recognition evaluation needs at least two identities with two images each.")

    detector = MTCNNFaceDetector(alignment_enabled=False)
    embedder = FaceNetEmbedder()
    embeddings: dict[str, list[np.ndarray]] = {}
    latencies: list[float] = []
    rejected_images = 0
    for identity, files in identities.items():
        vectors: list[np.ndarray] = []
        for path in files:
            started = time.perf_counter()
            content = path.read_bytes()
            detection = detector.detect_face(content, filename=path.name)
            if detection.face_count != 1 or detection.face_crop is None:
                rejected_images += 1
                continue
            crop = detection.face_crop
            if preprocessing == "aligned":
                image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
                if image is None or not detection.face_landmarks:
                    rejected_images += 1
                    continue
                crop = align_face(image, detection.face_landmarks)
            vectors.append(_normalized(embedder.generate_embedding(crop)))
            latencies.append((time.perf_counter() - started) * 1000.0)
        if len(vectors) >= 2:
            embeddings[identity] = vectors

    if len(embeddings) < 2:
        raise ValueError("Too few valid identities remained after face quality checks.")

    strategy_results: dict[str, object] = {}
    for strategy in sorted(SUPPORTED_AGGREGATIONS):
        genuine_scores: list[float] = []
        impostor_scores: list[float] = []
        for identity, probes in embeddings.items():
            for probe_index, probe in enumerate(probes):
                own_gallery = [item for index, item in enumerate(probes) if index != probe_index]
                genuine_scores.append(
                    aggregate_similarity(
                        probe,
                        own_gallery,
                        strategy=strategy,
                        top_k=top_k,
                    )
                )
                other_scores = [
                    aggregate_similarity(
                        probe,
                        gallery,
                        strategy=strategy,
                        top_k=top_k,
                    )
                    for other_identity, gallery in embeddings.items()
                    if other_identity != identity
                ]
                impostor_scores.append(max(other_scores))

        point = _eer_point(genuine_scores, impostor_scores)
        configured = _metrics_at_threshold(
            genuine_scores,
            impostor_scores,
            float(get_settings().FACE_RECOGNITION_THRESHOLD),
        )
        separation_margin = min(genuine_scores) - max(impostor_scores)
        strategy_results[strategy] = {
            **asdict(point),
            "genuine_attempts": len(genuine_scores),
            "impostor_attempts": len(impostor_scores),
            "genuine_score_min": min(genuine_scores),
            "genuine_score_median": float(np.median(genuine_scores)),
            "impostor_score_max": max(impostor_scores),
            "impostor_score_median": float(np.median(impostor_scores)),
            "separation_margin": separation_margin,
            "configured_threshold_metrics": asdict(configured),
        }

    best_strategy = min(
        strategy_results,
        key=lambda name: (
            strategy_results[name]["eer"],  # type: ignore[index]
            strategy_results[name]["false_accept_rate"],  # type: ignore[index]
            strategy_results[name]["false_reject_rate"],  # type: ignore[index]
            -strategy_results[name]["separation_margin"],  # type: ignore[index]
        ),
    )
    return {
        "dataset_type": "local_leave_one_out_enrollment_images",
        "identity_count": len(embeddings),
        "valid_image_count": sum(len(items) for items in embeddings.values()),
        "rejected_image_count": rejected_images,
        "preprocessing_version": (
            ALIGNED_PREPROCESSING_VERSION
            if preprocessing == "aligned"
            else LEGACY_PREPROCESSING_VERSION
        ),
        "model_name": (
            f"{embedder.model_name}-aligned-v2"
            if preprocessing == "aligned" and not embedder.model_name.endswith("-aligned-v2")
            else embedder.model_name
        ),
        "top_k": top_k,
        "average_extraction_latency_ms": (
            float(np.mean(latencies)) if latencies else None
        ),
        "selected_strategy": best_strategy,
        "strategies": strategy_results,
        "limitations": (
            "Enrollment images are not an independent holdout set; these results are optimistic "
            "and must be confirmed with separate appearance-variation probes."
        ),
    }


def _attempt_directories(root: Path) -> list[Path]:
    return sorted(
        directory
        for directory in root.rglob("*")
        if directory.is_dir() and _image_files(directory)
    )


def evaluate_pad(root: Path) -> dict[str, object]:
    real_root = root / "real"
    spoof_root = root / "spoof"
    if not real_root.exists() or not spoof_root.exists():
        raise ValueError("PAD data requires pad/real and pad/spoof attempt directories.")

    detector = MTCNNFaceDetector(alignment_enabled=False)
    service = OnnxFaceAntiSpoofingService(
        detector=detector,
        require_calibration=False,
    )

    def score_attempts(directories: list[Path]) -> tuple[list[float], list[float], int]:
        scores: list[float] = []
        latencies: list[float] = []
        rejected = 0
        for directory in directories:
            frames = [
                LivenessFrame(filename=path.name, content=path.read_bytes())
                for path in _image_files(directory)
            ]
            result = service.score_sequence(frames)
            if result.real_score is None:
                rejected += 1
                continue
            scores.append(result.real_score)
            latencies.append(result.latency_ms)
        return scores, latencies, rejected

    real_scores, real_latencies, rejected_real = score_attempts(_attempt_directories(real_root))
    spoof_scores, spoof_latencies, rejected_spoof = score_attempts(_attempt_directories(spoof_root))
    if not real_scores or not spoof_scores:
        raise ValueError("PAD calibration needs valid real and spoof camera attempts.")

    points = [
        point
        for point in _operating_points(real_scores, spoof_scores)
        if 0.0 < point.threshold < 1.0
    ]
    if not points:
        raise ValueError("PAD scores did not produce a valid probability threshold.")
    selected = min(
        points,
        key=lambda item: (
            (item.false_accept_rate + item.false_reject_rate) / 2.0,
            item.false_accept_rate,
            item.false_reject_rate,
            -item.threshold,
        ),
    )
    eer = _eer_point(real_scores, spoof_scores)
    return {
        "model_name": get_settings().FACE_ANTI_SPOOF_MODEL_NAME,
        "model_sha384": _sha384(
            resolve_project_path(get_settings().FACE_ANTI_SPOOF_MODEL_PATH)
        ),
        "aggregation": "median",
        "threshold_selection_policy": (
            "minimum ACER, then minimum APCER, then minimum BPCER, then higher threshold"
        ),
        "real_attempts_total": len(_attempt_directories(real_root)),
        "spoof_attempts_total": len(_attempt_directories(spoof_root)),
        "real_attempts": len(real_scores),
        "spoof_attempts": len(spoof_scores),
        "rejected_real_attempts": rejected_real,
        "rejected_spoof_attempts": rejected_spoof,
        "threshold": selected.threshold,
        "apcer_spoof_false_accept_rate": selected.false_accept_rate,
        "bpcer_live_false_reject_rate": selected.false_reject_rate,
        "acer": (selected.false_accept_rate + selected.false_reject_rate) / 2.0,
        "eer": eer.eer,
        "eer_threshold": eer.threshold,
        "live_acceptance_rate": selected.true_accept_rate,
        "spoof_rejection_rate": selected.true_reject_rate,
        "average_sequence_latency_ms": float(np.mean(real_latencies + spoof_latencies)),
        "limitations": (
            "RGB passive PAD is camera and scene dependent. Include phone, tablet, print, "
            "and replay attempts captured by the deployment camera."
        ),
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recognition-root", type=Path)
    parser.add_argument("--pad-root", type=Path)
    parser.add_argument("--preprocessing", choices=("legacy", "aligned"), default="legacy")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--write-recognition-calibration", type=Path)
    parser.add_argument("--write-pad-calibration", type=Path)
    parser.add_argument(
        "--confirm-local-validation",
        action="store_true",
        help="Required before writing an operational calibration file.",
    )
    args = parser.parse_args()
    if not args.recognition_root and not args.pad_root:
        parser.error("Provide --recognition-root and/or --pad-root.")
    if args.top_k < 1:
        parser.error("--top-k must be at least 1.")

    report: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if args.recognition_root:
        report["recognition"] = evaluate_recognition(
            resolve_project_path(args.recognition_root),
            preprocessing=args.preprocessing,
            top_k=args.top_k,
        )
    if args.pad_root:
        report["presentation_attack_detection"] = evaluate_pad(
            resolve_project_path(args.pad_root)
        )

    if args.write_recognition_calibration or args.write_pad_calibration:
        if not args.confirm_local_validation:
            parser.error("Calibration output requires --confirm-local-validation.")
    if args.write_recognition_calibration:
        recognition = report.get("recognition")
        if not isinstance(recognition, dict):
            parser.error("Recognition calibration requires --recognition-root.")
        selected_name = str(recognition["selected_strategy"])
        selected = recognition["strategies"][selected_name]
        _write_json(
            resolve_project_path(args.write_recognition_calibration),
            {
                "validated": True,
                "generated_at": report["generated_at"],
                "model_name": recognition["model_name"],
                "preprocessing_version": recognition["preprocessing_version"],
                "aggregation": selected_name,
                "top_k": recognition["top_k"],
                "threshold": selected["threshold"],
                "ambiguity_margin": get_settings().FACE_RECOGNITION_AMBIGUITY_MARGIN,
                "genuine_attempts": selected["genuine_attempts"],
                "impostor_attempts": selected["impostor_attempts"],
                "far": selected["false_accept_rate"],
                "frr": selected["false_reject_rate"],
                "dataset_limitation": recognition["limitations"],
            },
        )
    if args.write_pad_calibration:
        pad = report.get("presentation_attack_detection")
        if not isinstance(pad, dict):
            parser.error("PAD calibration requires --pad-root.")
        if (
            int(pad["real_attempts"]) < MIN_PAD_CALIBRATION_ATTEMPTS_PER_CLASS
            or int(pad["spoof_attempts"]) < MIN_PAD_CALIBRATION_ATTEMPTS_PER_CLASS
        ):
            parser.error(
                "Operational PAD calibration requires at least "
                f"{MIN_PAD_CALIBRATION_ATTEMPTS_PER_CLASS} valid real attempts and "
                f"{MIN_PAD_CALIBRATION_ATTEMPTS_PER_CLASS} valid spoof attempts."
            )
        _write_json(
            resolve_project_path(args.write_pad_calibration),
            {
                "validated": True,
                "generated_at": report["generated_at"],
                "model_name": pad["model_name"],
                "model_sha384": pad["model_sha384"],
                "aggregation": pad["aggregation"],
                "threshold": pad["threshold"],
                "real_attempts": pad["real_attempts"],
                "spoof_attempts": pad["spoof_attempts"],
                "apcer": pad["apcer_spoof_false_accept_rate"],
                "bpcer": pad["bpcer_live_false_reject_rate"],
                "acer": pad["acer"],
                "eer": pad["eer"],
                "eer_threshold": pad["eer_threshold"],
                "live_acceptance_rate": pad["live_acceptance_rate"],
                "spoof_rejection_rate": pad["spoof_rejection_rate"],
                "average_sequence_latency_ms": pad["average_sequence_latency_ms"],
                "threshold_selection_policy": pad["threshold_selection_policy"],
            },
        )

    if args.report:
        _write_json(resolve_project_path(args.report), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
