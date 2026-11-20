"""FaceNet ONNX embedder adapter."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.config import get_settings
from app.domain.services.face_processing_service import FaceEmbedderInterface
from app.infrastructure.face_ai.face_alignment import validate_preprocessing_model_identity


class FaceNetEmbedder(FaceEmbedderInterface):
    """Generate normalized 512-dimensional FaceNet embeddings with ONNX Runtime."""

    def __init__(self) -> None:
        settings = get_settings()
        self._model_name = settings.FACE_FACENET_MODEL_NAME
        self._model_path = Path(settings.FACE_FACENET_MODEL_PATH).expanduser().resolve()
        self._device = settings.FACE_FACENET_DEVICE.strip().lower()
        validate_preprocessing_model_identity(
            alignment_enabled=settings.FACE_ALIGNMENT_ENABLED,
            model_name=self._model_name,
        )

        if self._device != "cpu":
            raise RuntimeError("Only FACE_FACENET_DEVICE=cpu is supported by this ONNX setup.")
        if not self._model_path.exists():
            raise RuntimeError(
                f"FaceNet model file was not found at {self._model_path}. "
                "Download facenet.onnx before starting the application."
            )

        try:
            import onnxruntime as ort
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "FaceNet embedder backend is configured but onnxruntime is not installed."
            ) from error

        try:
            self._session = ort.InferenceSession(
                str(self._model_path),
                providers=["CPUExecutionProvider"],
            )
        except Exception as error:
            raise RuntimeError("FaceNet ONNX model failed to initialize.") from error

        self._input_name = self._session.get_inputs()[0].name
        self._output_name = self._session.get_outputs()[0].name

    @property
    def model_name(self) -> str:
        return self._model_name

    def generate_embedding(self, face_image) -> list[float]:
        if face_image is None or getattr(face_image, "size", 0) == 0:
            raise ValueError("Invalid face image")

        tensor = self._preprocess(face_image)
        output = self._session.run([self._output_name], {self._input_name: tensor})[0]
        embedding = output.reshape(-1).astype(np.float32)
        if embedding.size == 0 or not np.isfinite(embedding).all():
            raise ValueError("Failed to generate a valid FaceNet embedding")

        norm = float(np.linalg.norm(embedding))
        if norm <= 0:
            raise ValueError("Failed to normalize FaceNet embedding")

        normalized = embedding / norm
        return normalized.astype(float).tolist()

    @staticmethod
    def _preprocess(face_image) -> np.ndarray:
        face_rgb = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(face_rgb, (160, 160), interpolation=cv2.INTER_AREA)
        tensor = resized.astype(np.float32) / 255.0
        tensor = (tensor - 0.5) / 0.5
        tensor = np.transpose(tensor, (2, 0, 1))
        return np.expand_dims(tensor, axis=0).astype(np.float32)
