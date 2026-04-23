"""
services/face_service.py
─────────────────────────────────────────────────────────────
ML inference service + MJPEG frame generator.

Responsibilities
────────────────
• Load Keras model, LabelEncoder, StandardScaler once at startup
• Load MediaPipe FaceLandmarker once at startup
• Run CLAHE → landmark detection → feature extraction → prediction
  (identical preprocessing to src/collect.py + src/extract.py)
• Maintain a 15-frame rolling prediction buffer for temporal smoothing
• Write attendance via attendance_service when a confident match fires
• Yield JPEG-encoded frames for the MJPEG streaming endpoint
─────────────────────────────────────────────────────────────
"""

import logging
import os
import pickle
import time
from collections import deque
from datetime import datetime
from typing import Generator, Optional

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from tensorflow.keras.models import load_model as keras_load_model

from services.attendance_service import write_record
from utils.drawing import draw_face_box, draw_landmarks
from utils.features import extract_features

logger = logging.getLogger(__name__)

# ── Project-root-relative model paths ───────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_H5    = os.path.join(BASE_DIR, "models", "face_model.h5")
ENCODER_PKL = os.path.join(BASE_DIR, "models", "label_encoder.pkl")
SCALER_PKL  = os.path.join(BASE_DIR, "models", "scaler.pkl")
TASK_FILE   = os.path.join(BASE_DIR, "models", "face_landmarker.task")

# ── Tunable inference constants ──────────────────────────────
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.92"))
RECOGNITION_COOLDOWN = int(os.getenv("RECOGNITION_COOLDOWN", "3"))   # seconds
BUFFER_SIZE          = int(os.getenv("BUFFER_SIZE", "15"))           # frames
WEBCAM_INDEX         = int(os.getenv("WEBCAM_INDEX", "0"))
FRAME_WIDTH          = int(os.getenv("FRAME_WIDTH", "1280"))
FRAME_HEIGHT         = int(os.getenv("FRAME_HEIGHT", "720"))


class FaceService:
    """
    Singleton-style service loaded once at application startup via lifespan.

    All heavy objects (Keras model, MediaPipe detector, OpenCV capture)
    live inside this instance and are never re-created per request.
    """

    def __init__(self) -> None:
        self._model_ready = False
        self._cap: Optional[cv2.VideoCapture] = None

        # Inference state
        self._pred_buffer: deque = deque(maxlen=BUFFER_SIZE)
        self._last_logged: dict  = {}     # name → timestamp of last log write
        self._latest_frame: Optional[bytes] = None  # last JPEG for MJPEG stream

        # Load ML artefacts
        self._load_models()

        # CLAHE — same params as collect.py and extract.py
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    # ── Model loading (called once at startup) ────────────────
    def _load_models(self) -> None:
        """Load Keras model, label encoder, scaler, and MediaPipe detector."""
        missing = [
            (MODEL_H5,    "Run src/train.py first"),
            (ENCODER_PKL, "Run src/train.py first"),
            (SCALER_PKL,  "Run src/train.py first"),
            (TASK_FILE,   "Run python setup.py first"),
        ]
        for path, hint in missing:
            if not os.path.exists(path):
                logger.error("Missing model file: %s  → %s", path, hint)
                return

        self._keras_model = keras_load_model(MODEL_H5, compile=False)

        with open(ENCODER_PKL, "rb") as f:
            self._label_encoder = pickle.load(f)

        with open(SCALER_PKL, "rb") as f:
            self._scaler = pickle.load(f)

        # MediaPipe: low detection thresholds to catch angled/far faces
        base_opts = mp_python.BaseOptions(model_asset_path=TASK_FILE)
        mp_opts   = vision.FaceLandmarkerOptions(
            base_options=base_opts,
            num_faces=1,
            min_face_detection_confidence=0.3,
            min_face_presence_confidence=0.3,
            min_tracking_confidence=0.3,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=True,
        )
        self._detector = vision.FaceLandmarker.create_from_options(mp_opts)

        self._model_ready = True
        logger.info(
            "FaceService ready — %d known persons: %s",
            len(self._label_encoder.classes_),
            list(self._label_encoder.classes_),
        )

    @property
    def is_ready(self) -> bool:
        return self._model_ready

    @property
    def known_persons(self) -> list:
        if not self._model_ready:
            return []
        return [c.replace("_", " ") for c in self._label_encoder.classes_]

    # ── Webcam lifecycle ──────────────────────────────────────
    def open_camera(self) -> bool:
        """Open the webcam. Returns True on success."""
        if self._cap and self._cap.isOpened():
            return True
        self._cap = cv2.VideoCapture(WEBCAM_INDEX)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        ok = self._cap.isOpened()
        if not ok:
            logger.error("Failed to open webcam index %d", WEBCAM_INDEX)
        return ok

    def close_camera(self) -> None:
        if self._cap and self._cap.isOpened():
            self._cap.release()
        self._cap = None

    def close(self) -> None:
        """Release all resources — called at app shutdown."""
        self.close_camera()
        if self._model_ready:
            self._detector.close()
        logger.info("FaceService shut down.")

    # ── Single-frame inference ────────────────────────────────
    def _process_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Apply CLAHE → MediaPipe → Keras prediction → draw overlay.
        Writes attendance CSV when a confident, cooled-down match fires.
        Returns the annotated BGR frame.
        """
        frame = cv2.flip(frame, 1)

        # CLAHE low-light enhancement (must match collect.py exactly)
        lab        = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b_ch = cv2.split(lab)
        lab2       = cv2.merge([self._clahe.apply(l), a, b_ch])
        enhanced   = cv2.cvtColor(lab2, cv2.COLOR_LAB2BGR)

        rgb      = cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result   = self._detector.detect(mp_image)

        face_found = bool(result.face_landmarks)

        if face_found and self._model_ready:
            face_lm = result.face_landmarks[0]
            matrix  = (result.facial_transformation_matrixes[0]
                       if result.facial_transformation_matrixes else None)

            pts = draw_landmarks(enhanced, face_lm)

            # Feature extraction → scale → predict
            feats        = extract_features(face_lm, matrix)
            feats_scaled = self._scaler.transform(
                np.array([feats], dtype=np.float32)
            )
            pred = self._keras_model.predict(feats_scaled, verbose=0)[0]
            self._pred_buffer.append(pred)

            # Temporal smoothing over rolling buffer
            avg_pred   = np.mean(self._pred_buffer, axis=0)
            label_id   = int(np.argmax(avg_pred))
            confidence = float(avg_pred[label_id])

            if confidence >= CONFIDENCE_THRESHOLD:
                raw_name   = self._label_encoder.classes_[label_id]
                name_label = raw_name.replace("_", " ")
                box_color  = (0, 255, 80)

                # Write log at most once per RECOGNITION_COOLDOWN seconds
                now = time.time()
                if (raw_name not in self._last_logged or
                        now - self._last_logged[raw_name] >= RECOGNITION_COOLDOWN):
                    try:
                        write_record(raw_name)
                        self._last_logged[raw_name] = now
                        logger.info(
                            "Attendance logged: %s  conf=%.2f",
                            name_label, confidence,
                        )
                    except Exception as exc:
                        logger.error("Log write failed: %s", exc)
            else:
                name_label = "Unknown"
                box_color  = (0, 80, 255)
                self._pred_buffer.clear()   # reset on unknown

            draw_face_box(enhanced, pts, name_label, confidence, box_color)

            # HUD — confidence bar
            self._draw_confidence_bar(enhanced, confidence)
        else:
            self._pred_buffer.clear()      # reset when face leaves frame

        self._draw_top_bar(enhanced)
        return enhanced

    # ── MJPEG frame generator ─────────────────────────────────
    def generate_frames(self) -> Generator[bytes, None, None]:
        """
        Yield multipart MJPEG frames for StreamingResponse.
        Opens the webcam on first call; releases on generator exit.
        """
        if not self.open_camera():
            return

        try:
            while True:
                ret, frame = self._cap.read()
                if not ret:
                    logger.warning("Webcam read failed — stopping stream.")
                    break

                annotated = self._process_frame(frame)
                ok, jpeg  = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ok:
                    continue

                self._latest_frame = jpeg.tobytes()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + self._latest_frame
                    + b"\r\n"
                )
        finally:
            self.close_camera()

    # ── HUD helpers ───────────────────────────────────────────
    def _draw_top_bar(self, frame: np.ndarray) -> None:
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (0, 0), (w, 52), (15, 15, 20), -1)
        cv2.putText(frame, "FACE RECOGNITION ATTENDANCE",
                    (12, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 220, 255), 2)
        cv2.putText(frame, datetime.now().strftime("%H:%M:%S"),
                    (12, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (120, 120, 120), 1)
        if self._model_ready:
            txt = f"Known: {len(self._label_encoder.classes_)}"
            cv2.putText(frame, txt, (w - 130, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (80, 200, 80), 1)

    def _draw_confidence_bar(self, frame: np.ndarray, confidence: float) -> None:
        h, w = frame.shape[:2]
        bar_w = int(w * confidence)
        color = (0, 200, 80) if confidence >= CONFIDENCE_THRESHOLD else (0, 80, 200)
        cv2.rectangle(frame, (0, h - 6), (bar_w, h), color, -1)
        cv2.rectangle(frame, (0, h - 6), (w, h), (40, 40, 40), 1)
