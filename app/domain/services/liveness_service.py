"""Liveness detection contracts for live camera attendance."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional


class LivenessChallengeType(StrEnum):
    """Supported MVP challenge-response liveness prompts."""

    BLINK = "BLINK"
    TURN_HEAD_LEFT = "TURN_HEAD_LEFT"
    TURN_HEAD_RIGHT = "TURN_HEAD_RIGHT"


@dataclass(frozen=True)
class LivenessFrame:
    """One encoded camera frame submitted for liveness validation."""

    filename: str
    content: bytes


@dataclass(frozen=True)
class LivenessValidationRequest:
    """Frame sequence and requested challenge."""

    frames: list[LivenessFrame]
    challenge_type: str


@dataclass(frozen=True)
class LivenessValidationResult:
    """Safe liveness result returned to the application layer."""

    passed: bool
    challenge_type: str
    confidence: float
    frames_analyzed: int
    selected_frame: Optional[LivenessFrame] = None
    failure_reason: Optional[str] = None


class LivenessServiceInterface(ABC):
    """Validate that a frame sequence contains a live person."""

    @abstractmethod
    def validate(self, request: LivenessValidationRequest) -> LivenessValidationResult:
        """Validate liveness and return the best frame for recognition."""
        raise NotImplementedError
