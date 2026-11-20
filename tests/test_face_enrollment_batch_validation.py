from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.application.dto.face_enrollment_dto import (
    EnrollEmployeeFaceRequest,
    ReEnrollEmployeeFaceRequest,
)
from app.application.use_cases.exceptions import FaceEnrollmentValidationError
from app.application.use_cases.face_enrollment.enroll_employee_face import EnrollEmployeeFace
from app.application.use_cases.face_enrollment.re_enroll_employee_face import (
    ReEnrollEmployeeFace,
)
from app.domain.services.face_processing_service import (
    FaceDetectionResult,
    FaceEnrollmentBatchValidationError,
    FaceImageData,
    FaceImageValidationIssue,
)
from app.infrastructure.face_ai.face_enrollment_service import FaceEnrollmentService
from app.infrastructure.face_ai.face_quality import FaceQualityResult
from app.infrastructure.face_ai.image_validator import ImageValidator
from app.presentation.api.face_enrollment import _raise_http_error


def _images(*names: str) -> list[FaceImageData]:
    return [FaceImageData(filename=name, content=f"content:{name}".encode()) for name in names]


class _Detector:
    def __init__(self) -> None:
        self.results: dict[str, FaceDetectionResult] = {}
        self.calls: list[str] = []

    def detect_face(self, image_bytes, *, employee_id=None, filename=None):
        _ = image_bytes, employee_id
        image_name = filename or "unknown.jpg"
        self.calls.append(image_name)
        return self.results.get(
            image_name,
            FaceDetectionResult(face_count=1, face_crop=image_name),
        )


class _QualityValidator:
    def __init__(self) -> None:
        self.rejections: dict[str, str] = {}

    def assess(self, detection):
        reason = self.rejections.get(str(detection.face_crop))
        return FaceQualityResult(accepted=reason is None, reason=reason)


class _Embedder:
    model_name = "facenet-test-model"

    def __init__(self) -> None:
        self.calls: list[object] = []

    def generate_embedding(self, face_image):
        self.calls.append(face_image)
        return [1.0, float(len(self.calls))]


class _Storage:
    def __init__(self) -> None:
        self.saved: list[str] = []
        self.deleted: list[str] = []

    def save_employee_face_image(
        self,
        *,
        employee_id,
        image_bytes,
        original_filename,
        index,
    ):
        _ = image_bytes
        path = f"employee_{employee_id}/{index}_{original_filename}"
        self.saved.append(path)
        return path

    def delete_files(self, relative_paths):
        self.deleted.extend(relative_paths)


class _FaceEmbeddingRepository:
    def __init__(self, *, active_count: int = 0) -> None:
        self.active_count = active_count
        self.created_batches: list[list[dict]] = []
        self.deactivate_calls = 0

    def count_active_by_employee_id(self, employee_id):
        _ = employee_id
        return self.active_count

    def create_many_embeddings(self, *, embeddings, commit=True):
        assert commit is True
        self.created_batches.append(list(embeddings))
        self.active_count = len(embeddings)
        return [SimpleNamespace(**embedding) for embedding in embeddings]

    def get_active_model_names_by_employee_id(self, employee_id):
        _ = employee_id
        return ["facenet-test-model"] if self.active_count else []

    def get_active_embedding_vectors_by_employee_id(self, employee_id, *, model_name):
        _ = employee_id, model_name
        return [[1.0, 0.0]] if self.active_count else []

    def deactivate_active_by_employee_id(self, employee_id, *, commit=True):
        _ = employee_id, commit
        previous = self.active_count
        self.active_count = 0
        self.deactivate_calls += 1
        return previous


class _SimilarityService:
    def validate_embeddings(self, embeddings):
        assert embeddings

    def are_same_person(self, embeddings):
        _ = embeddings
        return True

    def matches_existing_template(self, *, new_embeddings, existing_embeddings):
        _ = new_embeddings, existing_embeddings
        return True


class _AuditRepository:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def log(self, **values):
        self.entries.append(values)


def _service():
    detector = _Detector()
    quality = _QualityValidator()
    embedder = _Embedder()
    storage = _Storage()
    service = FaceEnrollmentService(
        image_validator=ImageValidator(),
        detector=detector,
        embedder=embedder,
        storage_service=storage,
        quality_validator=quality,
    )
    service._min_images = 1
    service._max_images = 10
    service._quality_enabled = True
    return service, detector, quality, embedder, storage


def test_five_valid_images_generate_the_complete_temporary_batch():
    service, detector, quality, embedder, storage = _service()
    _ = detector, quality
    images = _images("photo_1.jpg", "photo_2.jpg", "photo_3.jpg", "photo_4.jpg", "photo_5.jpg")

    generated = service.validate_and_generate_embeddings(employee_id=1, images=images)

    assert [item.filename for item in generated] == [item.filename for item in images]
    assert len(embedder.calls) == 5
    assert storage.saved == []


def test_all_invalid_images_are_reported_by_original_filename_before_facenet_runs():
    service, detector, quality, embedder, storage = _service()
    quality.rejections["photo_2.jpg"] = "The image is too blurred for reliable enrollment."
    detector.results["photo_4.jpg"] = FaceDetectionResult(face_count=0)
    detector.results["photo_5.jpg"] = FaceDetectionResult(face_count=2)
    images = _images("photo_1.jpg", "photo_2.jpg", "photo_3.jpg", "photo_4.jpg", "photo_5.jpg")

    with pytest.raises(FaceEnrollmentBatchValidationError) as captured:
        service.validate_and_generate_embeddings(employee_id=1, images=images)

    issues = captured.value.issues
    assert [(issue.filename, issue.code, issue.position) for issue in issues] == [
        ("photo_2.jpg", "IMAGE_TOO_BLURRED", 2),
        ("photo_4.jpg", "NO_FACE", 4),
        ("photo_5.jpg", "MULTIPLE_FACES", 5),
    ]
    assert "sharper photo" in issues[0].message
    assert "employee's face" in issues[1].message
    assert "only this employee" in issues[2].message
    assert len(detector.calls) == 5
    assert embedder.calls == []
    assert storage.saved == []


def test_failed_initial_enrollment_persists_nothing_and_retry_saves_full_batch():
    service, detector, quality, embedder, storage = _service()
    _ = detector, embedder
    images = _images("photo_1.jpg", "photo_2.jpg", "photo_3.jpg", "photo_4.jpg", "photo_5.jpg")
    quality.rejections["photo_2.jpg"] = "The image is too blurred for reliable enrollment."
    face_repo = _FaceEmbeddingRepository()
    audit_repo = _AuditRepository()
    use_case = EnrollEmployeeFace(
        employee_repo=SimpleNamespace(
            get_by_id=lambda employee_id: SimpleNamespace(
                id=employee_id,
                full_name="Employee One",
                is_active=True,
            )
        ),
        face_embedding_repo=face_repo,
        face_enrollment_service=service,
        face_similarity_service=_SimilarityService(),
        audit_repo=audit_repo,
    )
    request = EnrollEmployeeFaceRequest(
        employee_id=1,
        images=images,
        actor_user_id=99,
    )

    with pytest.raises(FaceEnrollmentValidationError):
        use_case.execute(request)

    assert face_repo.active_count == 0
    assert face_repo.created_batches == []
    assert storage.saved == []
    assert audit_repo.entries == []

    quality.rejections.clear()
    result = use_case.execute(request)

    assert result.enrolled_images == 5
    assert result.active_embeddings == 5
    assert len(face_repo.created_batches) == 1
    assert len(face_repo.created_batches[0]) == 5
    assert len(storage.saved) == 5
    assert [entry["action"] for entry in audit_repo.entries] == ["ENROLL_FACE"]


def test_failed_re_enrollment_leaves_existing_active_enrollment_unchanged():
    service, detector, quality, embedder, storage = _service()
    _ = detector, embedder
    quality.rejections["replacement_3.jpg"] = "The face is too small. Please use a closer image."
    face_repo = _FaceEmbeddingRepository(active_count=2)
    audit_repo = _AuditRepository()
    use_case = ReEnrollEmployeeFace(
        employee_repo=SimpleNamespace(
            get_by_id=lambda employee_id: SimpleNamespace(
                id=employee_id,
                full_name="Employee One",
                is_active=True,
            )
        ),
        face_embedding_repo=face_repo,
        face_enrollment_service=service,
        face_similarity_service=_SimilarityService(),
        audit_repo=audit_repo,
    )

    with pytest.raises(FaceEnrollmentValidationError):
        use_case.execute(
            ReEnrollEmployeeFaceRequest(
                employee_id=1,
                images=_images(
                    "replacement_1.jpg",
                    "replacement_2.jpg",
                    "replacement_3.jpg",
                    "replacement_4.jpg",
                    "replacement_5.jpg",
                ),
                actor_user_id=99,
            )
        )

    assert face_repo.active_count == 2
    assert face_repo.deactivate_calls == 0
    assert face_repo.created_batches == []
    assert storage.saved == []
    assert audit_repo.entries == []


def test_http_error_contains_safe_structured_per_file_details():
    error = FaceEnrollmentValidationError(
        (
            FaceImageValidationIssue(
                filename="photo_2.jpg",
                code="IMAGE_TOO_BLURRED",
                message="Too blurred for reliable enrollment.",
                position=2,
            ),
        )
    )

    with pytest.raises(HTTPException) as captured:
        _raise_http_error(error)

    assert captured.value.status_code == 400
    assert captured.value.detail == {
        "success": False,
        "message": "Some enrollment images need attention.",
        "errors": [
            {
                "filename": "photo_2.jpg",
                "code": "IMAGE_TOO_BLURRED",
                "message": "Too blurred for reliable enrollment.",
                "position": 2,
            }
        ],
    }
    assert "embedding" not in str(captured.value.detail).lower()
