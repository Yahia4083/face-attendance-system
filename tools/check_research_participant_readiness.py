"""Validate one research participant before camera experiments begin.

The check is read-only.  Enrolled participants must have enough active FaceNet
templates for the fixed protocol, while UNKNOWN holdouts must have no active
face templates at all.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.infrastructure.database.connection import SessionLocal  # noqa: E402
from app.infrastructure.database.repositories.sql_employee_repository import (  # noqa: E402
    SqlEmployeeRepository,
)
from app.infrastructure.database.repositories.sql_face_embedding_repository import (  # noqa: E402
    SqlFaceEmbeddingRepository,
)


UNKNOWN_IDENTITY = "UNKNOWN"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participant-id", required=True)
    parser.add_argument("--expected-employee-number", required=True)
    parser.add_argument("--group", choices=("enrolled", "unknown"), required=True)
    parser.add_argument("--minimum-enrollment-embeddings", type=int, default=5)
    args = parser.parse_args()
    if args.minimum_enrollment_embeddings < 1:
        parser.error("--minimum-enrollment-embeddings must be at least 1.")
    return args


def main() -> int:
    args = _parse_args()
    database = SessionLocal()
    try:
        employee_repo = SqlEmployeeRepository(database)
        embedding_repo = SqlFaceEmbeddingRepository(database)

        if args.group == "enrolled":
            if args.expected_employee_number.upper() == UNKNOWN_IDENTITY:
                raise ValueError("An enrolled participant cannot use expected identity UNKNOWN.")
            employee = employee_repo.get_by_employee_number(args.expected_employee_number)
            if employee is None:
                raise ValueError(
                    f"Participant {args.participant_id}: employee number "
                    f"{args.expected_employee_number!r} does not exist."
                )
            if not employee.is_active:
                raise ValueError(
                    f"Participant {args.participant_id}: employee "
                    f"{args.expected_employee_number!r} is inactive."
                )
            model_name = get_settings().FACE_FACENET_MODEL_NAME
            compatible = embedding_repo.get_active_embedding_vectors_by_employee_id(
                employee.id,
                model_name=model_name,
            )
            if len(compatible) < args.minimum_enrollment_embeddings:
                raise ValueError(
                    f"Participant {args.participant_id}: employee "
                    f"{args.expected_employee_number!r} has {len(compatible)} active compatible "
                    f"FaceNet embedding(s), but this protocol requires at least "
                    f"{args.minimum_enrollment_embeddings}. Complete or repeat face enrollment first."
                )
            print(
                f"PARTICIPANT READY: {args.participant_id} -> "
                f"{args.expected_employee_number} ({len(compatible)} compatible embeddings)"
            )
            return 0

        if args.expected_employee_number.upper() != UNKNOWN_IDENTITY:
            raise ValueError("An unknown holdout must use expected identity UNKNOWN.")

        # An unknown holdout may also have an administrative employee row.
        # They remain biometric unknowns only while they have zero active templates.
        holdout_employee = employee_repo.get_by_employee_number(args.participant_id)
        active_count = (
            embedding_repo.count_active_by_employee_id(holdout_employee.id)
            if holdout_employee is not None
            else 0
        )
        if active_count:
            raise ValueError(
                f"Participant {args.participant_id} is reserved as UNKNOWN but has "
                f"{active_count} active face embedding(s). Do not collect unknown trials until "
                "those templates are removed or the holdout assignment is changed."
            )
        print(f"PARTICIPANT READY: {args.participant_id} is an UNKNOWN biometric holdout")
        return 0
    except ValueError as error:
        print(f"PARTICIPANT NOT READY: {error}", file=sys.stderr)
        return 2
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
