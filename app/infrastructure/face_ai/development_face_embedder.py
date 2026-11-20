"""Development-safe face embedder adapter."""

import cv2
import numpy as np

from app.domain.services.face_processing_service import FaceEmbedderInterface


class DevelopmentFaceEmbedder(FaceEmbedderInterface):
    """Deterministic lightweight embedder for development environments."""

    @property
    def model_name(self) -> str:
        return "development-face-embedder-v1"

    def generate_embedding(self, face_image) -> list[float]:
        if face_image is None or getattr(face_image, "size", 0) == 0:
            raise ValueError("Invalid face image")

        gray = cv2.cvtColor(face_image, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (64, 64))

        hist = cv2.calcHist([resized], [0], None, [64], [0, 256]).flatten()
        blocks = resized.reshape(8, 8, 8, 8).mean(axis=(1, 3)).flatten()
        embedding = np.concatenate((hist, blocks)).astype(np.float32)

        norm = float(np.linalg.norm(embedding))
        if norm > 0:
            embedding = embedding / norm

        return embedding.tolist()

