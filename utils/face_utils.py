"""
utils/face_utils.py
────────────────────────────────────────────────────────────
Shared helpers for face detection, alignment, quality checks,
and landmark drawing — used by all pipeline scripts.
────────────────────────────────────────────────────────────
"""

import cv2
import dlib
import numpy as np
from imutils import face_utils
import os
from dotenv import load_dotenv

load_dotenv()

SHAPE_PREDICTOR_PATH = os.getenv("SHAPE_PREDICTOR_PATH", "./shape_predictor_68_face_landmarks.dat")
MIN_FACE_SIZE        = int(os.getenv("MIN_FACE_SIZE", 80))
BLUR_THRESHOLD       = float(os.getenv("BLUR_THRESHOLD", 80.0))

# ── Landmark group indices (dlib 68-point model) ─────────
LANDMARK_GROUPS = {
    "jaw":          list(range(0,  17)),
    "right_brow":   list(range(17, 22)),
    "left_brow":    list(range(22, 27)),
    "nose_bridge":  list(range(27, 31)),
    "nose_tip":     list(range(31, 36)),
    "right_eye":    list(range(36, 42)),
    "left_eye":     list(range(42, 48)),
    "outer_lip":    list(range(48, 60)),
    "inner_lip":    list(range(60, 68)),
}

GROUP_COLORS = {
    "jaw":          (180, 180, 180),
    "right_brow":   (0,   200, 255),
    "left_brow":    (0,   200, 255),
    "nose_bridge":  (255, 180,  50),
    "nose_tip":     (255, 180,  50),
    "right_eye":    (50,  255, 150),
    "left_eye":     (50,  255, 150),
    "outer_lip":    (80,  80,  255),
    "inner_lip":    (150, 100, 255),
}


class FaceAnalyzer:
    """
    Wraps dlib detector + shape predictor.
    Single instance shared across all scripts.
    """

    def __init__(self):
        if not os.path.exists(SHAPE_PREDICTOR_PATH):
            raise FileNotFoundError(
                f"\n[ERROR] Missing: {SHAPE_PREDICTOR_PATH}\n"
                "Download from: https://github.com/davisking/dlib-models\n"
                "File: shape_predictor_68_face_landmarks.dat.bz2 → extract and place in project root."
            )
        self.detector  = dlib.get_frontal_face_detector()
        self.predictor = dlib.shape_predictor(SHAPE_PREDICTOR_PATH)

    def detect(self, gray_frame, upsample=0):
        """Return list of dlib rectangles for all faces found."""
        return self.detector(gray_frame, upsample)

    def landmarks(self, gray_frame, rect):
        """Return (68, 2) numpy array of landmark (x, y) points."""
        shape = self.predictor(gray_frame, rect)
        return face_utils.shape_to_np(shape)

    def align_face(self, frame, rect, output_size=160):
        """
        Align face using eye centres so the face is always
        upright — critical for consistent recognition accuracy.
        Returns aligned BGR crop of size (output_size, output_size).
        """
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        pts   = self.landmarks(gray, rect)

        # Eye centre points
        l_eye = pts[36:42].mean(axis=0)
        r_eye = pts[42:48].mean(axis=0)

        # Compute rotation angle
        dy    = r_eye[1] - l_eye[1]
        dx    = r_eye[0] - l_eye[0]
        angle = np.degrees(np.arctan2(dy, dx))

        # Centre between eyes
        eye_centre = ((l_eye[0] + r_eye[0]) / 2,
                      (l_eye[1] + r_eye[1]) / 2)

        # Rotation matrix + warp
        M       = cv2.getRotationMatrix2D(eye_centre, angle, scale=1.0)
        aligned = cv2.warpAffine(frame, M, (frame.shape[1], frame.shape[0]),
                                 flags=cv2.INTER_CUBIC)

        # Crop the face ROI
        x1 = max(0, rect.left())
        y1 = max(0, rect.top())
        x2 = min(frame.shape[1], rect.right())
        y2 = min(frame.shape[0], rect.bottom())

        # Add 20% padding
        pad_x = int((x2 - x1) * 0.20)
        pad_y = int((y2 - y1) * 0.20)
        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(frame.shape[1], x2 + pad_x)
        y2 = min(frame.shape[0], y2 + pad_y)

        crop = aligned[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        return cv2.resize(crop, (output_size, output_size))


# ── Quality checks ────────────────────────────────────────

def blur_score(image):
    """Laplacian variance — higher = sharper image."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    return cv2.Laplacian(gray, cv2.CV_64F).var()

def is_blurry(image):
    return blur_score(image) < BLUR_THRESHOLD

def is_too_small(rect):
    w = rect.right()  - rect.left()
    h = rect.bottom() - rect.top()
    return w < MIN_FACE_SIZE or h < MIN_FACE_SIZE


# ── Drawing helpers ───────────────────────────────────────

def draw_landmarks(frame, pts, draw_lines=True):
    """
    Draw all 68 landmarks with colour-coded groups and
    connecting lines for jaw, eyebrows, eyes, nose, lips.
    """
    for group, indices in LANDMARK_GROUPS.items():
        color  = GROUP_COLORS[group]
        coords = [tuple(pts[i]) for i in indices]

        if draw_lines and group != "jaw":
            closed = group in ("right_eye", "left_eye", "outer_lip", "inner_lip")
            pts_arr = np.array(coords, dtype=np.int32)
            cv2.polylines(frame, [pts_arr], isClosed=closed,
                          color=color, thickness=1, lineType=cv2.LINE_AA)

        for (x, y) in coords:
            cv2.circle(frame, (x, y), 2, color, -1, lineType=cv2.LINE_AA)

    # Jaw line separately
    jaw_pts = np.array([tuple(pts[i]) for i in LANDMARK_GROUPS["jaw"]], dtype=np.int32)
    cv2.polylines(frame, [jaw_pts], isClosed=False,
                  color=GROUP_COLORS["jaw"], thickness=1, lineType=cv2.LINE_AA)


def draw_face_box(frame, rect, color=(0, 220, 255), label=None, confidence=None):
    """Draw bounding box with corner accents and optional label."""
    x1, y1 = rect.left(),  rect.top()
    x2, y2 = rect.right(), rect.bottom()

    # Main rectangle (thin)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)

    # Corner accents
    clen = 18
    thick = 2
    for cx, cy, dx, dy in [
        (x1, y1,  1,  1), (x2, y1, -1,  1),
        (x1, y2,  1, -1), (x2, y2, -1, -1),
    ]:
        cv2.line(frame, (cx, cy), (cx + dx * clen, cy),         color, thick, cv2.LINE_AA)
        cv2.line(frame, (cx, cy), (cx, cy + dy * clen),         color, thick, cv2.LINE_AA)

    if label:
        conf_str = f"  {confidence:.0f}%" if confidence is not None else ""
        text     = f"{label}{conf_str}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 8, y1), color, -1)
        cv2.putText(frame, text, (x1 + 4, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (10, 10, 10), 1, cv2.LINE_AA)


def draw_hud(frame, lines, position="top"):
    """Draw a semi-transparent HUD banner with multiple text lines."""
    h, w = frame.shape[:2]
    line_h = 28
    banner_h = len(lines) * line_h + 14
    overlay = frame.copy()

    if position == "top":
        cv2.rectangle(overlay, (0, 0), (w, banner_h), (10, 10, 10), -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
        for i, (text, color) in enumerate(lines):
            y = 20 + i * line_h
            cv2.putText(frame, text, (12, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)
    else:  # bottom
        y0 = h - banner_h
        cv2.rectangle(overlay, (0, y0), (w, h), (10, 10, 10), -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
        for i, (text, color) in enumerate(lines):
            y = y0 + 20 + i * line_h
            cv2.putText(frame, text, (12, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)