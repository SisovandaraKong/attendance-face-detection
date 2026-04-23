"""
utils/features.py
─────────────────────────────────────────────────────────────
Single source of truth for feature extraction.

Used by:
  • src/extract.py  — batch extraction from dataset images
  • services/face_service.py — real-time inference in the web app

DO NOT duplicate this logic anywhere else. Any change here
automatically propagates to both training and inference.
─────────────────────────────────────────────────────────────
"""

import math
from typing import Optional, List

import numpy as np

# ── Key landmark pairs for inter-landmark distance features ──
# Each tuple (a, b) measures a geometrically meaningful distance
# that is scale-invariant when normalised by face width.
KEY_DISTANCES: List[tuple] = [
    (33,  263),   # left eye outer → right eye outer  (eye span)
    (362, 133),   # right eye inner → left eye inner  (inner eye gap)
    (1,   4),     # nose bridge → nose tip
    (0,   17),    # upper lip → lower lip
    (61,  291),   # left mouth corner → right mouth corner
    (234, 454),   # left cheek → right cheek
    (10,  152),   # forehead → chin  (face height)
    (70,  300),   # left brow → right brow
    (6,   197),   # glabella → nose bridge
    (13,  14),    # inner upper lip → inner lower lip
]

# Total feature dimensions (must stay in sync with training)
FEATURE_SIZE = 478 * 3 + len(KEY_DISTANCES) + 3  # 1447


def extract_features(
    face_lm_list,
    transformation_matrix=None,
) -> List[float]:
    """
    Build the 1447-dimensional feature vector from MediaPipe landmarks.

    Components
    ----------
    1. Normalised (x, y, z) for all 478 landmarks  → 1434 values
       Normalised to [0, 1] within each axis using bounding-box range,
       making the features invariant to absolute face position and scale.

    2. 10 key inter-landmark 3-D Euclidean distances → 10 values
       Each distance normalised by face width (range_x) for scale invariance.

    3. Head pose angles (yaw, pitch, roll) from transformation matrix → 3 values
       Normalised to [-1, 1] by dividing degrees by 90.
       Falls back to [0, 0, 0] when matrix is unavailable.

    Parameters
    ----------
    face_lm_list        : MediaPipe NormalizedLandmarkList (478 landmarks)
    transformation_matrix : MediaPipe facial_transformation_matrixes entry, optional

    Returns
    -------
    List[float] of length FEATURE_SIZE (1447)
    """
    lms = face_lm_list

    xs = [lm.x for lm in lms]
    ys = [lm.y for lm in lms]
    zs = [lm.z for lm in lms]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)

    # Guard against zero-range (degenerate detection)
    range_x = max_x - min_x or 1e-6
    range_y = max_y - min_y or 1e-6
    range_z = max_z - min_z or 1e-6

    # ── 1. Normalised coordinates ────────────────────────────
    coords: List[float] = []
    for lm in lms:
        coords.append((lm.x - min_x) / range_x)
        coords.append((lm.y - min_y) / range_y)
        coords.append((lm.z - min_z) / range_z)

    # ── 2. Scale-invariant key distances ────────────────────
    face_w = range_x  # already guaranteed non-zero above
    dists: List[float] = []
    for a, b in KEY_DISTANCES:
        if a < len(lms) and b < len(lms):
            dx = lms[a].x - lms[b].x
            dy = lms[a].y - lms[b].y
            dz = lms[a].z - lms[b].z
            dists.append(math.sqrt(dx * dx + dy * dy + dz * dz) / face_w)
        else:
            dists.append(0.0)

    # ── 3. Head pose angles from rotation matrix ─────────────
    angles: List[float] = [0.0, 0.0, 0.0]
    if transformation_matrix is not None:
        try:
            mat = np.array(transformation_matrix.data).reshape(4, 4)
            R = mat[:3, :3]
            pitch = math.atan2(-R[2, 0], math.sqrt(R[2, 1] ** 2 + R[2, 2] ** 2))
            yaw   = math.atan2(R[1, 0], R[0, 0])
            roll  = math.atan2(R[2, 1], R[2, 2])
            angles = [
                math.degrees(yaw)   / 90.0,
                math.degrees(pitch) / 90.0,
                math.degrees(roll)  / 90.0,
            ]
        except Exception:
            # Malformed matrix — silently fall back to zeros
            pass

    return coords + dists + angles
