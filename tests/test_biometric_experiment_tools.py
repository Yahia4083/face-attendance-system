from __future__ import annotations

import numpy as np
import pytest

from tools import run_biometric_experiments as experiments
from tools.run_biometric_experiments import liveness_outcome, recognition_outcome
from tools.summarize_biometric_experiments import summarize, wilson_interval


def test_research_camera_reader_reopens_a_stale_virtual_camera(monkeypatch):
    first_frame = np.full((4, 6, 3), 40, dtype=np.uint8)
    recovered_frame = np.full((4, 6, 3), 180, dtype=np.uint8)
    captures = []
    readers = []

    class FakeCapture:
        def __init__(self, index):
            self.index = index
            self.released = False

        def isOpened(self):
            return True

        def release(self):
            self.released = True

    class FakeReader:
        def __init__(self, capture, **_kwargs):
            self.capture = capture
            self.closed = False
            readers.append(self)

        def start(self):
            return self

        def snapshot(self, *, now=None):
            if self.capture.index == 0:
                return experiments.CameraFrameSnapshot(
                    frame=first_frame,
                    sequence=2,
                    camera_available=False,
                    consecutive_failures=30,
                )
            return experiments.CameraFrameSnapshot(
                frame=recovered_frame,
                sequence=1,
                camera_available=True,
                consecutive_failures=0,
            )

        def close(self):
            self.closed = True

    def fake_open_camera(_source):
        capture = FakeCapture(len(captures))
        captures.append(capture)
        return capture

    monkeypatch.setattr(experiments, "CameraFrameReader", FakeReader)

    reader = experiments.RecoveringCameraReader(
        0,
        rotate=0,
        flip=False,
        unavailable_after=30,
        stale_after_seconds=2.0,
        recovery_seconds=2.0,
        open_camera=fake_open_camera,
    ).start()
    unavailable = reader.snapshot(now=10.0)
    assert unavailable.camera_available is False
    assert np.array_equal(unavailable.frame, first_frame)
    assert readers[0].closed is True
    assert len(captures) == 1

    still_waiting = reader.snapshot(now=11.9)
    assert still_waiting.camera_available is False
    assert len(captures) == 1

    recovered = reader.snapshot(now=12.0)
    assert recovered.camera_available is True
    assert recovered.sequence == 3
    assert np.array_equal(recovered.frame, recovered_frame)
    assert len(captures) == 2
    reader.close()
    assert readers[1].closed is True


def test_research_camera_recovery_alternates_windows_backends(monkeypatch):
    opened_backends = []

    class FakeCapture:
        def __init__(self, _source, backend):
            opened_backends.append(backend)

        @staticmethod
        def isOpened():
            return True

        @staticmethod
        def release():
            pass

    monkeypatch.setattr(experiments.sys, "platform", "win32")
    monkeypatch.setattr(experiments.cv2, "VideoCapture", FakeCapture)
    reader = experiments.RecoveringCameraReader(
        0,
        rotate=0,
        flip=False,
        unavailable_after=30,
        stale_after_seconds=2.0,
        recovery_seconds=2.0,
    )

    reader._open_capture()
    reader._open_capture()

    assert opened_backends == [experiments.cv2.CAP_DSHOW, experiments.cv2.CAP_MSMF]


@pytest.mark.parametrize(
    ("expected", "accepted", "predicted", "acquisition", "outcome"),
    [
        ("EMP001", True, "EMP001", "usable", "TRUE_ACCEPT"),
        ("EMP001", False, "REJECT", "usable", "FALSE_REJECT"),
        ("EMP001", True, "EMP002", "usable", "MISIDENTIFICATION"),
        ("UNKNOWN", False, "REJECT", "usable", "TRUE_REJECT"),
        ("UNKNOWN", True, "EMP001", "usable", "FALSE_ACCEPT"),
        ("EMP001", False, "REJECT", "processing_rejected", "ACQUISITION_FAILURE"),
    ],
)
def test_recognition_outcome(expected, accepted, predicted, acquisition, outcome):
    assert (
        recognition_outcome(
            expected_identity=expected,
            accepted=accepted,
            predicted_identity=predicted,
            acquisition_result=acquisition,
        )
        == outcome
    )


@pytest.mark.parametrize(
    ("expected", "passed", "usable", "outcome"),
    [
        ("accept", True, True, "CORRECT_ACCEPT"),
        ("accept", False, True, "UNEXPECTED_REJECT"),
        ("reject", False, True, "CORRECT_REJECT"),
        ("reject", True, True, "UNEXPECTED_ACCEPT"),
        ("reject", False, False, "ACQUISITION_FAILURE"),
    ],
)
def test_liveness_outcome(expected, passed, usable, outcome):
    assert liveness_outcome(expected_decision=expected, passed=passed, usable=usable) == outcome


def _recognition_row(
    attempt_id: str,
    *,
    expected: str,
    enrollment_status: str,
    accepted: bool,
    outcome: str,
    condition: str,
    latency: float,
    acquisition: str = "usable",
):
    return {
        "attempt_id": attempt_id,
        "mode": "recognition",
        "expected_identity": expected,
        "enrollment_status": enrollment_status,
        "accepted": str(accepted).lower(),
        "outcome": outcome,
        "condition": condition,
        "acquisition_result": acquisition,
        "processing_ms": str(latency),
    }


def _liveness_row(
    attempt_id: str,
    *,
    scenario: str,
    expected: str,
    passed: bool,
    outcome: str,
    latency: float,
    acquisition: str = "usable",
):
    return {
        "attempt_id": attempt_id,
        "mode": "liveness",
        "scenario": scenario,
        "expected_decision": expected,
        "liveness_pass": str(passed).lower(),
        "accepted": str(passed).lower(),
        "outcome": outcome,
        "acquisition_result": acquisition,
        "processing_ms": str(latency),
        "total_ms": str(latency + 3000),
    }


def test_summary_reports_recognition_and_active_liveness_separately():
    rows = [
        _recognition_row(
            "R1",
            expected="EMP001",
            enrollment_status="enrolled",
            accepted=True,
            outcome="TRUE_ACCEPT",
            condition="frontal",
            latency=100,
        ),
        _recognition_row(
            "R2",
            expected="EMP001",
            enrollment_status="enrolled",
            accepted=False,
            outcome="FALSE_REJECT",
            condition="frontal",
            latency=120,
        ),
        _recognition_row(
            "R3",
            expected="EMP002",
            enrollment_status="enrolled",
            accepted=True,
            outcome="MISIDENTIFICATION",
            condition="pose_left",
            latency=130,
        ),
        _recognition_row(
            "R4",
            expected="UNKNOWN",
            enrollment_status="unknown",
            accepted=False,
            outcome="TRUE_REJECT",
            condition="unknown",
            latency=90,
        ),
        _recognition_row(
            "R5",
            expected="UNKNOWN",
            enrollment_status="unknown",
            accepted=True,
            outcome="FALSE_ACCEPT",
            condition="unknown",
            latency=110,
        ),
        _recognition_row(
            "R6",
            expected="EMP003",
            enrollment_status="enrolled",
            accepted=False,
            outcome="ACQUISITION_FAILURE",
            condition="near",
            latency=10,
            acquisition="processing_rejected",
        ),
        _liveness_row(
            "L1",
            scenario="correct",
            expected="accept",
            passed=True,
            outcome="CORRECT_ACCEPT",
            latency=200,
        ),
        _liveness_row(
            "L2",
            scenario="correct",
            expected="accept",
            passed=False,
            outcome="UNEXPECTED_REJECT",
            latency=210,
        ),
        _liveness_row(
            "L3",
            scenario="wrong_direction",
            expected="reject",
            passed=False,
            outcome="CORRECT_REJECT",
            latency=220,
        ),
        _liveness_row(
            "L4",
            scenario="wrong_direction",
            expected="reject",
            passed=True,
            outcome="UNEXPECTED_ACCEPT",
            latency=230,
        ),
        _liveness_row(
            "L5",
            scenario="phone_photo",
            expected="reject",
            passed=False,
            outcome="CORRECT_REJECT",
            latency=240,
        ),
        _liveness_row(
            "L6",
            scenario="phone_photo",
            expected="reject",
            passed=False,
            outcome="ACQUISITION_FAILURE",
            latency=5,
            acquisition="camera_failure",
        ),
    ]

    result = summarize(rows)
    recognition = result["recognition"]["overall"]
    assert recognition["attempts_total"] == 6
    assert recognition["usable_attempts"] == 5
    assert recognition["true_accepts"] == 1
    assert recognition["false_rejects"] == 2
    assert recognition["misidentifications"] == 1
    assert recognition["true_rejects"] == 1
    assert recognition["false_accepts"] == 1
    assert recognition["tar"]["rate"] == pytest.approx(1 / 3)
    assert recognition["frr"]["rate"] == pytest.approx(2 / 3)
    assert recognition["far"]["rate"] == pytest.approx(1 / 2)
    assert recognition["overall_decision_accuracy"]["rate"] == pytest.approx(2 / 5)
    assert recognition["failure_to_acquire"]["rate"] == pytest.approx(1 / 6)
    assert recognition["recognition_processing_latency"]["mean_ms"] == pytest.approx(110)

    liveness = result["active_liveness"]["overall"]
    assert liveness["attempts_total"] == 6
    assert liveness["usable_attempts"] == 5
    assert liveness["passes"] == 2
    assert liveness["rejections"] == 3
    assert liveness["liveness_success_rate"]["rate"] == pytest.approx(1 / 2)
    assert liveness["attack_rejection_rate"]["rate"] == pytest.approx(2 / 3)
    assert liveness["correct_decision_rate"]["rate"] == pytest.approx(3 / 5)
    assert liveness["failure_to_acquire"]["rate"] == pytest.approx(1 / 6)


def test_wilson_interval_does_not_claim_zero_population_error():
    zero_errors = wilson_interval(0, 20)
    all_successes = wilson_interval(20, 20)
    assert zero_errors is not None
    assert zero_errors[0] == 0
    assert zero_errors[1] == pytest.approx(0.1611, abs=0.0002)
    assert all_successes is not None
    assert all_successes[0] == pytest.approx(0.8389, abs=0.0002)
    assert all_successes[1] == 1


def test_summary_treats_no_face_phone_submission_as_fta_not_attack_rejection():
    no_face = _liveness_row(
        "L-NO-FACE",
        scenario="phone_photo",
        expected="reject",
        passed=False,
        outcome="CORRECT_REJECT",
        latency=5,
        acquisition="usable",
    )
    no_face["failure_reason"] = "No face detected in the captured sequence."
    no_face["liveness_failure_reason"] = "No face detected in the captured sequence."
    accepted_photo = _liveness_row(
        "L-PHOTO-ACCEPTED",
        scenario="phone_photo",
        expected="reject",
        passed=True,
        outcome="UNEXPECTED_ACCEPT",
        latency=200,
    )

    result = summarize([no_face, accepted_photo])
    phone = result["active_liveness"]["by_scenario"]["phone_photo"]
    overall = result["active_liveness"]["overall"]

    assert phone["attempts_total"] == 2
    assert phone["evaluable_attempts"] == 1
    assert phone["failure_to_acquire"]["count"] == 1
    assert phone["attack_rejection_rate"]["count"] == 0
    assert phone["attack_rejection_rate"]["total"] == 1
    assert overall["correct_decision_rate"]["count"] == 0
    assert overall["correct_decision_rate"]["total"] == 1
