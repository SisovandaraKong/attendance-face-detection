"""Lightweight landmark-based liveness checks for kiosk attendance."""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass
from math import dist


BLINK_EAR_THRESHOLD = float(os.getenv("LIVENESS_BLINK_EAR_THRESHOLD", "0.215"))
BLINK_MIN_CLOSED_FRAMES = max(int(os.getenv("LIVENESS_BLINK_MIN_CLOSED_FRAMES", "2")), 1)
HEAD_MOVEMENT_THRESHOLD = float(os.getenv("LIVENESS_HEAD_MOVEMENT_THRESHOLD", "0.025"))
LIVENESS_WINDOW_SECONDS = float(os.getenv("LIVENESS_WINDOW_SECONDS", "3.0"))
LIVENESS_MIN_STABLE_FRAMES = max(int(os.getenv("LIVENESS_MIN_STABLE_FRAMES", "4")), 1)
LIVENESS_PASS_SCORE = float(os.getenv("LIVENESS_PASS_SCORE", "0.6"))


LEFT_EYE_POINTS = (33, 159, 158, 133, 153, 145)
RIGHT_EYE_POINTS = (362, 386, 387, 263, 373, 380)
NOSE_TIP_INDEX = 1


@dataclass
class LivenessState:
    score: float
    passed: bool
    blink_detected: bool
    head_movement_detected: bool
    average_ear: float
    head_movement_range: float
    stable_frames: int
    message: str


def _eye_aspect_ratio(landmarks, indices: tuple[int, int, int, int, int, int]) -> float:
    p1 = landmarks[indices[0]]
    p2 = landmarks[indices[1]]
    p3 = landmarks[indices[2]]
    p4 = landmarks[indices[3]]
    p5 = landmarks[indices[4]]
    p6 = landmarks[indices[5]]

    horizontal = dist((p1.x, p1.y), (p4.x, p4.y))
    if horizontal == 0:
        return 0.0
    vertical = dist((p2.x, p2.y), (p6.x, p6.y)) + dist((p3.x, p3.y), (p5.x, p5.y))
    return vertical / (2.0 * horizontal)


class LandmarkLivenessTracker:
    """Track simple dynamic liveness cues from MediaPipe landmarks."""

    def __init__(self) -> None:
        self._nose_offsets: deque[tuple[float, float]] = deque()
        self._recent_blinks: deque[float] = deque()
        self._closed_frames = 0
        self._stable_frames = 0
        self._last_state = LivenessState(
            score=0.0,
            passed=False,
            blink_detected=False,
            head_movement_detected=False,
            average_ear=0.0,
            head_movement_range=0.0,
            stable_frames=0,
            message="Blink or turn your head slightly to confirm liveness.",
        )

    def reset(self) -> None:
        self._nose_offsets.clear()
        self._recent_blinks.clear()
        self._closed_frames = 0
        self._stable_frames = 0
        self._last_state = LivenessState(
            score=0.0,
            passed=False,
            blink_detected=False,
            head_movement_detected=False,
            average_ear=0.0,
            head_movement_range=0.0,
            stable_frames=0,
            message="Blink or turn your head slightly to confirm liveness.",
        )

    @property
    def last_state(self) -> LivenessState:
        return self._last_state

    def update(self, landmarks) -> LivenessState:
        now = time.time()
        self._stable_frames += 1

        left_ear = _eye_aspect_ratio(landmarks, LEFT_EYE_POINTS)
        right_ear = _eye_aspect_ratio(landmarks, RIGHT_EYE_POINTS)
        average_ear = (left_ear + right_ear) / 2.0

        xs = [lm.x for lm in landmarks]
        face_center_x = (min(xs) + max(xs)) / 2.0
        face_width = max(max(xs) - min(xs), 1e-6)
        nose_offset = (landmarks[NOSE_TIP_INDEX].x - face_center_x) / face_width
        self._nose_offsets.append((now, nose_offset))

        while self._nose_offsets and now - self._nose_offsets[0][0] > LIVENESS_WINDOW_SECONDS:
            self._nose_offsets.popleft()
        while self._recent_blinks and now - self._recent_blinks[0] > LIVENESS_WINDOW_SECONDS:
            self._recent_blinks.popleft()

        if average_ear < BLINK_EAR_THRESHOLD:
            self._closed_frames += 1
        else:
            if self._closed_frames >= BLINK_MIN_CLOSED_FRAMES:
                self._recent_blinks.append(now)
            self._closed_frames = 0

        blink_detected = bool(self._recent_blinks)
        head_offsets = [offset for _, offset in self._nose_offsets]
        head_movement_range = max(head_offsets) - min(head_offsets) if head_offsets else 0.0
        head_movement_detected = head_movement_range >= HEAD_MOVEMENT_THRESHOLD

        score = 0.0
        if blink_detected:
            score += 0.6
        if head_movement_detected:
            score += 0.4

        passed = self._stable_frames >= LIVENESS_MIN_STABLE_FRAMES and score >= LIVENESS_PASS_SCORE
        if passed:
            message = "Liveness confirmed."
        elif self._stable_frames < LIVENESS_MIN_STABLE_FRAMES:
            message = "Hold still for a moment, then blink or turn your head slightly."
        else:
            message = "Liveness not confirmed. Please blink or turn your head slightly."

        self._last_state = LivenessState(
            score=min(score, 1.0),
            passed=passed,
            blink_detected=blink_detected,
            head_movement_detected=head_movement_detected,
            average_ear=average_ear,
            head_movement_range=head_movement_range,
            stable_frames=self._stable_frames,
            message=message,
        )
        return self._last_state
