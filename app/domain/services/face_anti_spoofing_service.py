"""Presentation-attack detection contracts for live attendance."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from app.domain.services.liveness_service import LivenessFrame


class AntiSpoofFailureCategory(str, Enum):
    """Classify safe PAD failures without exposing model internals."""

    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    FRAME_VALIDATION = "FRAME_VALIDATION"
    PRESENTATION_ATTACK = "PRESENTATION_ATTACK"


@dataclass(frozen=True)
class AntiSpoofResult:
    """Safe passive liveness decision without exposing biometric material."""

    is_live: bool
    model_name: str
    frames_analyzed: int
    confidence: float | None = None
    failure_reason: str | None = None
    failure_category: AntiSpoofFailureCategory | None = None
    latency_ms: float | None = None


class FaceAntiSpoofingServiceInterface(ABC):
    """Evaluate a camera frame sequence for RGB presentation attacks."""

    @abstractmethod
    def evaluate(self, frames: list[LivenessFrame]) -> AntiSpoofResult:
        """Return a calibrated sequence-level live/spoof decision."""
        raise NotImplementedError
