from types import SimpleNamespace

import pytest

from tools import check_research_participant_readiness as readiness


class FakeDatabase:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    employee: SimpleNamespace | None,
    compatible_count: int = 0,
    active_count: int = 0,
) -> FakeDatabase:
    database = FakeDatabase()

    class FakeEmployeeRepository:
        def __init__(self, _database: FakeDatabase) -> None:
            pass

        def get_by_employee_number(self, _employee_number: str) -> SimpleNamespace | None:
            return employee

    class FakeEmbeddingRepository:
        def __init__(self, _database: FakeDatabase) -> None:
            pass

        def get_active_embedding_vectors_by_employee_id(
            self,
            _employee_id: int,
            *,
            model_name: str,
        ) -> list[list[float]]:
            assert model_name == "facenet-test"
            return [[0.0]] * compatible_count

        def count_active_by_employee_id(self, _employee_id: int) -> int:
            return active_count

    monkeypatch.setattr(readiness, "SessionLocal", lambda: database)
    monkeypatch.setattr(readiness, "SqlEmployeeRepository", FakeEmployeeRepository)
    monkeypatch.setattr(readiness, "SqlFaceEmbeddingRepository", FakeEmbeddingRepository)
    monkeypatch.setattr(
        readiness,
        "get_settings",
        lambda: SimpleNamespace(FACE_FACENET_MODEL_NAME="facenet-test"),
    )
    return database


def test_enrolled_participant_is_ready_with_five_compatible_embeddings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = _install_fakes(
        monkeypatch,
        employee=SimpleNamespace(id=7, is_active=True),
        compatible_count=5,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_research_participant_readiness.py",
            "--participant-id",
            "P02",
            "--expected-employee-number",
            "P02",
            "--group",
            "enrolled",
        ],
    )

    assert readiness.main() == 0
    assert "PARTICIPANT READY" in capsys.readouterr().out
    assert database.closed


def test_enrolled_participant_is_blocked_when_templates_are_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = _install_fakes(
        monkeypatch,
        employee=SimpleNamespace(id=7, is_active=True),
        compatible_count=4,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_research_participant_readiness.py",
            "--participant-id",
            "P02",
            "--expected-employee-number",
            "P02",
            "--group",
            "enrolled",
        ],
    )

    assert readiness.main() == 2
    assert "requires at least 5" in capsys.readouterr().err
    assert database.closed


@pytest.mark.parametrize(
    ("active_count", "expected_exit"),
    [(0, 0), (1, 2)],
)
def test_unknown_holdout_must_have_no_active_face_templates(
    monkeypatch: pytest.MonkeyPatch,
    active_count: int,
    expected_exit: int,
) -> None:
    database = _install_fakes(
        monkeypatch,
        employee=SimpleNamespace(id=11, is_active=True),
        active_count=active_count,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_research_participant_readiness.py",
            "--participant-id",
            "U01",
            "--expected-employee-number",
            "UNKNOWN",
            "--group",
            "unknown",
        ],
    )

    assert readiness.main() == expected_exit
    assert database.closed
