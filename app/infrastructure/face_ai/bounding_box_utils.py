"""Bounding-box helpers for OpenCV face detection."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

FaceBox = tuple[int, int, int, int]


@dataclass(frozen=True)
class FaceBoxCandidate:
    """One detected face normalized against its source frame."""

    box: FaceBox
    area: float
    area_ratio: float
    center_distance_ratio: float


def calculate_iou(first: FaceBox, second: FaceBox) -> float:
    """Return intersection-over-union for two ``(x, y, w, h)`` boxes."""
    first_x, first_y, first_w, first_h = first
    second_x, second_y, second_w, second_h = second

    left = max(first_x, second_x)
    top = max(first_y, second_y)
    right = min(first_x + first_w, second_x + second_w)
    bottom = min(first_y + first_h, second_y + second_h)

    intersection_width = max(0, right - left)
    intersection_height = max(0, bottom - top)
    intersection_area = intersection_width * intersection_height

    if intersection_area == 0:
        return 0.0

    first_area = first_w * first_h
    second_area = second_w * second_h
    union_area = first_area + second_area - intersection_area
    if union_area <= 0:
        return 0.0

    return intersection_area / union_area


def suppress_overlapping_boxes(
    boxes: Iterable[FaceBox],
    *,
    iou_threshold: float,
) -> list[FaceBox]:
    """Collapse strongly overlapping detections that represent the same face."""
    remaining = sorted(boxes, key=lambda box: box[2] * box[3], reverse=True)
    selected: list[FaceBox] = []

    while remaining:
        current = remaining.pop(0)
        selected.append(current)
        remaining = [
            candidate
            for candidate in remaining
            if calculate_iou(current, candidate) < iou_threshold
        ]

    return selected


def select_primary_face_box(
    boxes: Iterable[FaceBox],
    *,
    frame_size: tuple[int, int] | None,
    min_area_ratio: float,
    max_center_distance_ratio: float,
    dominance_ratio: float,
) -> FaceBox | None:
    """Select one dominant foreground face while ignoring tiny background faces."""
    candidates = _face_box_candidates(boxes, frame_size=frame_size)
    significant = [
        item
        for item in candidates
        if item.area_ratio >= min_area_ratio
        and item.center_distance_ratio <= max_center_distance_ratio
    ]
    significant.sort(key=lambda item: item.area, reverse=True)
    if len(significant) == 1:
        return significant[0].box
    if len(significant) < 2:
        return None
    if significant[0].area / max(significant[1].area, 1.0) >= dominance_ratio:
        return significant[0].box
    return None


def _face_box_candidates(
    boxes: Iterable[FaceBox],
    *,
    frame_size: tuple[int, int] | None,
) -> list[FaceBoxCandidate]:
    normalized_boxes = list(boxes)
    if not frame_size:
        return [
            FaceBoxCandidate(
                box=box,
                area=float(max(0, box[2]) * max(0, box[3])),
                area_ratio=1.0,
                center_distance_ratio=0.0,
            )
            for box in normalized_boxes
        ]

    frame_width, frame_height = frame_size
    frame_area = max(1.0, float(frame_width * frame_height))
    half_diagonal = max(1.0, math.hypot(frame_width, frame_height) / 2.0)
    center_x = frame_width / 2.0
    center_y = frame_height / 2.0
    candidates: list[FaceBoxCandidate] = []
    for box in normalized_boxes:
        x, y, width, height = box
        area = float(max(0, width) * max(0, height))
        distance = math.hypot(
            x + width / 2.0 - center_x,
            y + height / 2.0 - center_y,
        )
        candidates.append(
            FaceBoxCandidate(
                box=box,
                area=area,
                area_ratio=area / frame_area,
                center_distance_ratio=distance / half_diagonal,
            )
        )
    return candidates
