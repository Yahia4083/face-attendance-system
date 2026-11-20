"""Local storage service for enrolled face images."""

from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from app.config import get_settings
from app.domain.services.face_processing_service import FaceStorageServiceInterface


class FaceStorageService(FaceStorageServiceInterface):
    """Persist and cleanup face images in local storage."""

    _RELATIVE_STORAGE_ROOT = "storage"

    def __init__(self) -> None:
        settings = get_settings()
        self._storage_root = Path(settings.STORAGE_PATH).expanduser().resolve()

    def save_employee_face_image(
        self,
        *,
        employee_id: int,
        image_bytes: bytes,
        original_filename: str,
        index: int,
    ) -> str:
        _ = original_filename
        employee_dir = self._storage_root / "faces" / str(employee_id)
        employee_dir.mkdir(parents=True, exist_ok=True)

        decoded_image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded_image is None:
            raise ValueError("Invalid image file")

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        target_path = self._build_unique_path(employee_dir, employee_id, timestamp, index)
        if not cv2.imwrite(str(target_path), decoded_image):
            raise ValueError("Failed to save image file")

        return self._to_relative_db_path(target_path).as_posix()

    def delete_files(self, relative_paths: list[str]) -> None:
        for relative_path in relative_paths:
            path = self._resolve_storage_path(relative_path)
            if not self._is_inside_storage_root(path):
                continue
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass

    @staticmethod
    def _build_unique_path(
        employee_dir: Path,
        employee_id: int,
        timestamp: str,
        index: int,
    ) -> Path:
        candidate_index = index
        while True:
            filename = f"employee_{employee_id}_{timestamp}_{candidate_index:03d}.jpg"
            candidate = employee_dir / filename
            if not candidate.exists():
                return candidate
            candidate_index += 1

    def _to_relative_db_path(self, absolute_path: Path) -> Path:
        relative_to_storage = absolute_path.resolve().relative_to(self._storage_root)
        return Path(self._RELATIVE_STORAGE_ROOT) / relative_to_storage

    def _resolve_storage_path(self, relative_path: str) -> Path:
        path = Path(relative_path)
        if path.is_absolute():
            return path

        normalized = path
        if normalized.parts and normalized.parts[0] == self._RELATIVE_STORAGE_ROOT:
            normalized = Path(*normalized.parts[1:])

        return self._storage_root / normalized

    def _is_inside_storage_root(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self._storage_root)
        except ValueError:
            return False
        return True
