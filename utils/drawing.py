"""
utils/drawing.py
─────────────────────────────────────────────────────────────
Shared OpenCV drawing helpers for MediaPipe 478-point landmarks.

Used by:
  • src/collect.py
  • src/webcam.py
  • services/face_service.py
─────────────────────────────────────────────────────────────
"""

from typing import List, Tuple

import cv2
import numpy as np

# ── MediaPipe face mesh connection groups ────────────────────
# Indices match the 478-landmark face_landmarker.task model.
FACE_OVAL: List[Tuple[int, int]] = [
    (10, 338), (338, 297), (297, 332), (332, 284), (284, 251), (251, 389),
    (389, 356), (356, 454), (454, 323), (323, 361), (361, 288), (288, 397),
    (397, 365), (365, 379), (379, 378), (378, 400), (400, 377), (377, 152),
    (152, 148), (148, 176), (176, 149), (149, 150), (150, 136), (136, 172),
    (172, 58),  (58, 132),  (132, 93),  (93, 234),  (234, 127), (127, 162),
    (162, 21),  (21, 54),   (54, 103),  (103, 67),  (67, 109),  (109, 10),
]

LEFT_EYE: List[Tuple[int, int]] = [
    (33, 7),   (7, 163),   (163, 144), (144, 145), (145, 153), (153, 154),
    (154, 155), (155, 133), (33, 246),  (246, 161), (161, 160), (160, 159),
    (159, 158), (158, 157), (157, 173), (173, 133),
]

RIGHT_EYE: List[Tuple[int, int]] = [
    (362, 382), (382, 381), (381, 380), (380, 374), (374, 373), (373, 390),
    (390, 249), (249, 263), (362, 398), (398, 384), (384, 385), (385, 386),
    (386, 387), (387, 388), (388, 466), (466, 263),
]

LIPS: List[Tuple[int, int]] = [
    (61, 146),  (146, 91),  (91, 181),  (181, 84),  (84, 17),   (17, 314),
    (314, 405), (405, 321), (321, 375), (375, 291), (61, 185),  (185, 40),
    (40, 39),   (39, 37),   (37, 0),    (0, 267),   (267, 269), (269, 270),
    (270, 409), (409, 291),
]

NOSE: List[Tuple[int, int]] = [
    (168, 6), (6, 197), (197, 195), (195, 5), (5, 4), (4, 1), (1, 19), (19, 94), (94, 2),
]

ALL_CONNECTIONS: List[Tuple[int, int]] = FACE_OVAL + LEFT_EYE + RIGHT_EYE + LIPS + NOSE


def draw_landmarks(
    frame: np.ndarray,
    lms,
    color: Tuple[int, int, int] = (0, 220, 180),
) -> List[Tuple[int, int]]:
    """
    Draw 478-point MediaPipe landmarks on *frame* in-place.

    Returns the list of (x, y) pixel points so callers can derive
    bounding boxes without recomputing them.

    Parameters
    ----------
    frame   : BGR image (modified in-place)
    lms     : MediaPipe face landmarks list (478 NormalizedLandmark)
    color   : BGR connection-line colour

    Returns
    -------
    pts : List[Tuple[int, int]]  — pixel coordinates of all landmarks
    """
    h, w = frame.shape[:2]
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in lms]

    for a, b in ALL_CONNECTIONS:
        if a < len(pts) and b < len(pts):
            cv2.line(frame, pts[a], pts[b], color, 1, cv2.LINE_AA)

    for x, y in pts:
        cv2.circle(frame, (x, y), 1, (0, 255, 210), -1, cv2.LINE_AA)

    return pts


def draw_face_box(
    frame: np.ndarray,
    pts: List[Tuple[int, int]],
    label: str,
    confidence: float,
    color: Tuple[int, int, int] = (0, 255, 80),
) -> None:
    """
    Draw a bounding box derived from landmark pixel coordinates,
    with a filled label background above the box.

    Parameters
    ----------
    frame      : BGR image (modified in-place)
    pts        : pixel coordinates returned by draw_landmarks()
    label      : person name or "Unknown"
    confidence : 0.0–1.0 prediction confidence
    color      : BGR box and label background colour
    """
    h, w = frame.shape[:2]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]

    x1 = max(0, min(xs) - 20)
    y1 = max(0, min(ys) - 30)
    x2 = min(w, max(xs) + 20)
    y2 = min(h, max(ys) + 10)

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    label_txt = f"{label}  {confidence * 100:.0f}%"
    (tw, th), _ = cv2.getTextSize(label_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)
    cv2.rectangle(frame, (x1, y1 - th - 14), (x1 + tw + 10, y1), color, -1)
    cv2.putText(
        frame, label_txt, (x1 + 5, y1 - 5),
        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (10, 10, 10), 2, cv2.LINE_AA,
    )
