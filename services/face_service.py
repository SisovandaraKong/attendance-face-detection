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
• Maintain a rolling prediction buffer for temporal smoothing
• Write recognition events + attendance records when a confident match fires
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
from utils.liveness import LandmarkLivenessTracker

logger = logging.getLogger(__name__)

# ── Project-root-relative model paths ───────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_H5    = os.path.join(BASE_DIR, "models", "face_model.h5")
ENCODER_PKL = os.path.join(BASE_DIR, "models", "label_encoder.pkl")
SCALER_PKL  = os.path.join(BASE_DIR, "models", "scaler.pkl")
TASK_FILE   = os.path.join(BASE_DIR, "models", "face_landmarker.task")

# ── Tunable inference constants ──────────────────────────────
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.92"))
# Successful attendance confirmations should cool down briefly, but failed liveness
# checks should be retryable almost immediately so the kiosk feels responsive.
EVENT_EMIT_DEBOUNCE_SECONDS = max(float(os.getenv("EVENT_EMIT_DEBOUNCE_SECONDS", "1")), 0.5)
REJECTED_EVENT_RETRY_SECONDS = max(float(os.getenv("REJECTED_EVENT_RETRY_SECONDS", "0.75")), 0.1)
MAX_LIVENESS_FAILURES = max(int(os.getenv("MAX_LIVENESS_FAILURES", "3")), 1)
BUFFER_SIZE          = int(os.getenv("BUFFER_SIZE", "4"))            # frames
WEBCAM_INDEX         = int(os.getenv("WEBCAM_INDEX", "0"))
FRAME_WIDTH          = int(os.getenv("FRAME_WIDTH", "1280"))
FRAME_HEIGHT         = int(os.getenv("FRAME_HEIGHT", "720"))
LIVENESS_REQUIRED = os.getenv("LIVENESS_REQUIRED", "true").strip().lower() not in {"0", "false", "no"}


class FaceService:
    """
    Singleton-style service loaded once at application startup via lifespan.

    All heavy objects (Keras model, MediaPipe detector, OpenCV capture)
    live inside this instance and are never re-created per request.
    """

    def __init__(self) -> None:
        self._model_ready = False
        self._cap: Optional[cv2.VideoCapture] = None
        self._detector = None
        self._keras_model = None
        self._label_encoder = None
        self._scaler = None

        # Inference state
        self._pred_buffer: deque = deque(maxlen=BUFFER_SIZE)
        self._last_success_emitted: dict = {}  # name → timestamp of last accepted attendance confirmation
        self._last_rejected_emitted: dict = {}  # name → (timestamp, rejection status)
        self._liveness_fail_counts: dict = {}  # name → consecutive liveness failures before hard retry state
        self._latest_frame: Optional[bytes] = None  # last JPEG for MJPEG stream
        self._liveness_tracker = LandmarkLivenessTracker()
        self._public_status = {
            "state": "idle",
            "message": "Choose Check In or Check Out, then look at the camera.",
            "level": "info",
            "mode": None,
            "name": None,
            "liveness_score": 0.0,
            "liveness_passed": False,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

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

    @property
    def public_status(self) -> dict:
        return dict(self._public_status)

    def _set_public_status(
        self,
        *,
        state: str,
        message: str,
        level: str = "info",
        mode: str | None = None,
        name: str | None = None,
        liveness_score: float | None = None,
        liveness_passed: bool | None = None,
    ) -> None:
        self._public_status = {
            "state": state,
            "message": message,
            "level": level,
            "mode": mode,
            "name": name,
            "liveness_score": float(liveness_score or 0.0),
            "liveness_passed": bool(liveness_passed),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

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
        self._liveness_tracker.reset()
        if self._model_ready:
            self._detector.close()
        logger.info("FaceService shut down.")

    # ── Single-frame inference ────────────────────────────────
    def _process_frame(self, frame: np.ndarray, mode: str = "check-in") -> np.ndarray:
        """
        Apply CLAHE → MediaPipe → Keras prediction → draw overlay.
        Writes recognition event + attendance record on confident match.
        Returns the annotated BGR frame.
        """
        frame = cv2.flip(frame, 1)

        if not self._model_ready or self._detector is None:
            self._set_public_status(
                state="model_not_ready",
                message="Face model is not ready. Train and reload the backend first.",
                level="warn",
                mode=mode,
            )
            self._draw_top_bar(frame)
            return frame

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
            liveness = self._liveness_tracker.update(face_lm)

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
                box_color  = (0, 255, 80) if (not LIVENESS_REQUIRED or liveness.passed) else (0, 200, 255)

                # Debounce repeated frame-level detections before creating a new event.
                now = time.time()
                last_success_at = self._last_success_emitted.get(raw_name)
                recent_rejection = self._last_rejected_emitted.get(raw_name)
                rejection_blocks_retry = False
                if recent_rejection is not None:
                    rejected_at, rejected_status = recent_rejection
                    rejection_blocks_retry = (
                        now - rejected_at < REJECTED_EVENT_RETRY_SECONDS
                        and (rejected_status != "Liveness Failed" or not liveness.passed)
                    )

                if (
                    (last_success_at is None or now - last_success_at >= EVENT_EMIT_DEBOUNCE_SECONDS)
                    and not rejection_blocks_retry
                ):
                    try:
                        if LIVENESS_REQUIRED and not liveness.passed:
                            fail_count = self._liveness_fail_counts.get(raw_name, 0) + 1
                            self._liveness_fail_counts[raw_name] = fail_count

                            if fail_count < MAX_LIVENESS_FAILURES:
                                self._set_public_status(
                                    state="awaiting_liveness",
                                    message=(
                                        f"Liveness check {fail_count}/{MAX_LIVENESS_FAILURES}. "
                                        "Blink once or turn your head slightly."
                                    ),
                                    level="info",
                                    mode=mode,
                                    name=name_label,
                                    liveness_score=liveness.score,
                                    liveness_passed=False,
                                )
                            else:
                                record = write_record(
                                    raw_name,
                                    event_mode=mode,
                                    confidence=confidence,
                                    liveness_score=liveness.score,
                                    liveness_passed=False,
                                    liveness_message=liveness.message,
                                    source_id=f"camera:{WEBCAM_INDEX}",
                                )
                                self._last_rejected_emitted[raw_name] = (now, record.status)
                                self._liveness_fail_counts[raw_name] = 0
                                self._set_public_status(
                                    state="liveness_failed",
                                    message="Liveness failed 3 times. Please retry and look directly at the camera.",
                                    level="warn",
                                    mode=mode,
                                    name=name_label,
                                    liveness_score=liveness.score,
                                    liveness_passed=False,
                                )
                                logger.warning(
                                    "Recognition blocked by liveness after retries: %s  mode=%s  score=%.2f",
                                    name_label,
                                    mode,
                                    liveness.score,
                                )
                            draw_face_box(enhanced, pts, name_label, confidence, box_color)
                            self._draw_liveness_overlay(enhanced, liveness)
                            self._draw_confidence_bar(enhanced, confidence)
                            self._draw_top_bar(enhanced)
                            return enhanced

                        record = write_record(
                            raw_name,
                            event_mode=mode,
                            confidence=confidence,
                            liveness_score=liveness.score,
                            liveness_passed=(liveness.passed if LIVENESS_REQUIRED else True),
                            liveness_message=liveness.message,
                            source_id=f"camera:{WEBCAM_INDEX}",
                        )
                        self._liveness_fail_counts[raw_name] = 0
                        if record.status == "Liveness Failed":
                            self._last_rejected_emitted[raw_name] = (now, record.status)
                            self._set_public_status(
                                state="liveness_failed",
                                message="Attendance blocked: liveness was not confirmed. Please blink or turn your head slightly.",
                                level="warn",
                                mode=mode,
                                name=name_label,
                                liveness_score=liveness.score,
                                liveness_passed=False,
                            )
                            logger.warning(
                                "Recognition blocked by liveness: %s  mode=%s  score=%.2f",
                                name_label,
                                mode,
                                liveness.score,
                            )
                        elif record.status in {"Unrecognized", "Duplicate Ignored", "Outside Shift Window", "Rejected Event"}:
                            self._last_rejected_emitted[raw_name] = (now, record.status)
                            if record.status == "Unrecognized":
                                message = (
                                    f"{name_label} was recognized, but no employee record is registered yet."
                                )
                            else:
                                message = (
                                    f"Recognition captured for {name_label}, but attendance was not accepted: {record.status}."
                                )
                            self._set_public_status(
                                state="business_rejected",
                                message=message,
                                level="warn",
                                mode=mode,
                                name=name_label,
                                liveness_score=liveness.score,
                                liveness_passed=liveness.passed,
                            )
                            logger.warning(
                                "Recognition event did not create attendance: %s  mode=%s  status=%s  conf=%.2f",
                                name_label,
                                mode,
                                record.status,
                                confidence,
                            )
                        else:
                            self._last_success_emitted[raw_name] = now
                            self._last_rejected_emitted.pop(raw_name, None)
                            self._liveness_fail_counts[raw_name] = 0
                            self._set_public_status(
                                state="attendance_confirmed",
                                message=f"{record.status} recorded for {name_label}.",
                                level="ok",
                                mode=mode,
                                name=name_label,
                                liveness_score=liveness.score,
                                liveness_passed=liveness.passed,
                            )
                            logger.info(
                                "Attendance logged: %s  mode=%s  conf=%.2f  liveness=%.2f",
                                name_label,
                                mode,
                                confidence,
                                liveness.score,
                            )
                    except Exception as exc:
                        logger.error("Log write failed: %s", exc)
                else:
                    if LIVENESS_REQUIRED and not liveness.passed:
                        self._set_public_status(
                            state="awaiting_liveness",
                            message=liveness.message,
                            level="info",
                            mode=mode,
                            name=name_label,
                            liveness_score=liveness.score,
                            liveness_passed=False,
                        )
                    else:
                        self._set_public_status(
                            state="ready_to_confirm",
                            message=f"Recognition stable for {name_label}. Waiting for capture window.",
                            level="info",
                            mode=mode,
                            name=name_label,
                            liveness_score=liveness.score,
                            liveness_passed=liveness.passed,
                        )
            else:
                name_label = "Unknown"
                box_color  = (0, 80, 255)
                self._pred_buffer.clear()   # reset on unknown
                self._liveness_fail_counts.clear()
                self._set_public_status(
                    state="awaiting_recognition",
                    message="Face detected. Please face the camera, then blink or turn your head slightly.",
                    level="info",
                    mode=mode,
                    liveness_score=liveness.score,
                    liveness_passed=liveness.passed,
                )

            draw_face_box(enhanced, pts, name_label, confidence, box_color)
            self._draw_liveness_overlay(enhanced, liveness)

            # HUD — confidence bar
            self._draw_confidence_bar(enhanced, confidence)
        else:
            self._pred_buffer.clear()      # reset when face leaves frame
            self._liveness_tracker.reset()
            self._liveness_fail_counts.clear()
            self._set_public_status(
                state="waiting_for_face",
                message="Waiting for face. Stand in front of the camera, then blink or turn your head slightly.",
                level="info",
                mode=mode,
            )

        self._draw_top_bar(enhanced)
        return enhanced

    # ── MJPEG frame generator ─────────────────────────────────
    def generate_frames(self, mode: str = "check-in") -> Generator[bytes, None, None]:
        """
        Yield multipart MJPEG frames for StreamingResponse.
        Opens the webcam on first call; releases on generator exit.
        """
        if not self.open_camera():
            self._set_public_status(
                state="camera_unavailable",
                message="Camera could not be opened. Check the webcam device and try again.",
                level="warn",
                mode=mode,
            )
            return

        self._set_public_status(
            state="stream_started",
            message="Camera started. Look at the camera, then blink or turn your head slightly.",
            level="info",
            mode=mode,
        )

        try:
            while True:
                ret, frame = self._cap.read()
                if not ret:
                    logger.warning("Webcam read failed — stopping stream.")
                    self._set_public_status(
                        state="camera_read_failed",
                        message="Camera read failed. Restart the scan if needed.",
                        level="warn",
                        mode=mode,
                    )
                    break

                annotated = self._process_frame(frame, mode=mode)
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

    def _draw_liveness_overlay(self, frame: np.ndarray, liveness) -> None:
        h, _ = frame.shape[:2]
        panel_color = (0, 150, 80) if liveness.passed else (0, 150, 220)
        cv2.rectangle(frame, (14, h - 100), (380, h - 18), (18, 18, 24), -1)
        cv2.rectangle(frame, (14, h - 100), (380, h - 18), panel_color, 1)
        cv2.putText(
            frame,
            f"Liveness: {liveness.score * 100:.0f}% {'PASS' if liveness.passed else 'CHECK'}",
            (28, h - 72),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.56,
            panel_color,
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"Blink: {'yes' if liveness.blink_detected else 'no'}  Head move: {'yes' if liveness.head_movement_detected else 'no'}",
            (28, h - 46),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            (210, 210, 210),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            liveness.message[:52],
            (28, h - 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.44,
            (160, 160, 160),
            1,
            cv2.LINE_AA,
        )
