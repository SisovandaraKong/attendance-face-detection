"""Face quality, embedding, matching, and employee identification service."""

from __future__ import annotations

from dataclasses import dataclass
import pickle
from pathlib import Path
import os

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tensorflow.keras.models import Model, load_model

from app.models.employee import Employee
from utils.features import FEATURE_SIZE, extract_features


FACE_MATCH_THRESHOLD = 0.75
FACE_CLASSIFIER_THRESHOLD = float(os.getenv("FACE_CLASSIFIER_THRESHOLD", "0.75"))
MIN_FACE_WIDTH_RATIO = 0.18
MIN_FACE_HEIGHT_RATIO = 0.18
MIN_BLUR_VARIANCE = 45.0
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = Path(os.getenv("FACE_MODEL_DIR", str(PROJECT_ROOT / "models")))
FACE_LANDMARKER_MODEL_PATH = Path(
    os.getenv("FACE_LANDMARKER_MODEL_PATH", str(MODEL_DIR / "face_landmarker.task"))
)
FACE_CLASSIFIER_MODEL_PATH = Path(
    os.getenv("FACE_CLASSIFIER_MODEL_PATH", str(MODEL_DIR / "face_model.h5"))
)
FACE_LABEL_ENCODER_PATH = Path(
    os.getenv("FACE_LABEL_ENCODER_PATH", str(MODEL_DIR / "label_encoder.pkl"))
)
FACE_SCALER_PATH = Path(os.getenv("FACE_SCALER_PATH", str(MODEL_DIR / "scaler.pkl")))
FACE_STORAGE_DIR = Path(os.getenv("FACE_STORAGE_DIR", "storage/faces"))


@dataclass(frozen=True)
class FaceBox:
    x_min: int
    y_min: int
    x_max: int
    y_max: int

    @property
    def width(self) -> int:
        return max(self.x_max - self.x_min, 0)

    @property
    def height(self) -> int:
        return max(self.y_max - self.y_min, 0)


class FaceServiceError(RuntimeError):
    """Raised when image decoding or face processing cannot complete."""


_quality_face_landmarker: vision.FaceLandmarker | None = None
_face_landmarker: vision.FaceLandmarker | None = None
_classifier_model: Model | None = None
_label_encoder = None
_feature_scaler = None


def _ensure_landmarker_model() -> None:
    if not FACE_LANDMARKER_MODEL_PATH.exists():
        raise FaceServiceError(f"Face landmark model not found: {FACE_LANDMARKER_MODEL_PATH}")


def _to_mp_image(image_bgr: np.ndarray) -> mp.Image:
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)


def _get_quality_face_landmarker() -> vision.FaceLandmarker:
    global _quality_face_landmarker
    if _quality_face_landmarker is None:
        _ensure_landmarker_model()
        base_options = mp_python.BaseOptions(model_asset_path=str(FACE_LANDMARKER_MODEL_PATH))
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            num_faces=2,
            min_face_detection_confidence=0.55,
            min_face_presence_confidence=0.55,
            min_tracking_confidence=0.55,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        _quality_face_landmarker = vision.FaceLandmarker.create_from_options(options)
    return _quality_face_landmarker


def _get_face_landmarker() -> vision.FaceLandmarker:
    global _face_landmarker
    if _face_landmarker is None:
        _ensure_landmarker_model()
        base_options = mp_python.BaseOptions(model_asset_path=str(FACE_LANDMARKER_MODEL_PATH))
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            num_faces=1,
            min_face_detection_confidence=0.3,
            min_face_presence_confidence=0.3,
            min_tracking_confidence=0.3,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=True,
        )
        _face_landmarker = vision.FaceLandmarker.create_from_options(options)
    return _face_landmarker


def _get_classifier_bundle() -> tuple[Model | None, object | None, object | None]:
    global _classifier_model, _label_encoder, _feature_scaler
    if _classifier_model is None and FACE_CLASSIFIER_MODEL_PATH.exists():
        _classifier_model = load_model(FACE_CLASSIFIER_MODEL_PATH, compile=False)
    if _label_encoder is None and FACE_LABEL_ENCODER_PATH.exists():
        with FACE_LABEL_ENCODER_PATH.open("rb") as handle:
            _label_encoder = pickle.load(handle)
    if _feature_scaler is None and FACE_SCALER_PATH.exists():
        with FACE_SCALER_PATH.open("rb") as handle:
            _feature_scaler = pickle.load(handle)
    return _classifier_model, _label_encoder, _feature_scaler


def _decode_image(image_bytes: bytes) -> np.ndarray:
    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise FaceServiceError("Invalid image file")
    return image


def _detect_faces(image_bgr: np.ndarray) -> tuple[list[FaceBox], list[float]]:
    height, width = image_bgr.shape[:2]
    result = _get_quality_face_landmarker().detect(_to_mp_image(image_bgr))
    if not result.face_landmarks:
        return [], []

    boxes: list[FaceBox] = []
    confidences: list[float] = []
    for landmarks in result.face_landmarks:
        x_values = [landmark.x for landmark in landmarks]
        y_values = [landmark.y for landmark in landmarks]
        x_min = max(int(min(x_values) * width), 0)
        y_min = max(int(min(y_values) * height), 0)
        x_max = min(int(max(x_values) * width), width)
        y_max = min(int(max(y_values) * height), height)
        boxes.append(FaceBox(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max))
        confidences.append(1.0)
    return boxes, confidences


def _blur_variance(face_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _is_frontal_face(image_bgr: np.ndarray) -> bool:
    result = _get_quality_face_landmarker().detect(_to_mp_image(image_bgr))
    if not result.face_landmarks or len(result.face_landmarks) != 1:
        return False

    landmarks = result.face_landmarks[0]
    left_eye = landmarks[33]
    right_eye = landmarks[263]
    nose = landmarks[1]
    mouth_left = landmarks[61]
    mouth_right = landmarks[291]

    eye_center_x = (left_eye.x + right_eye.x) / 2
    mouth_center_x = (mouth_left.x + mouth_right.x) / 2
    eye_distance = abs(right_eye.x - left_eye.x)
    if eye_distance <= 0:
        return False

    nose_offset = abs(nose.x - eye_center_x) / eye_distance
    mouth_offset = abs(mouth_center_x - eye_center_x) / eye_distance
    eye_level_diff = abs(left_eye.y - right_eye.y) / eye_distance

    return nose_offset < 0.18 and mouth_offset < 0.22 and eye_level_diff < 0.14


def _largest_face_crop(image_bgr: np.ndarray) -> np.ndarray:
    boxes, _ = _detect_faces(image_bgr)
    if not boxes:
        raise FaceServiceError("No face detected")
    face_box = max(boxes, key=lambda box: box.width * box.height)
    crop = image_bgr[face_box.y_min : face_box.y_max, face_box.x_min : face_box.x_max]
    if crop.size == 0:
        raise FaceServiceError("Detected face crop is empty")
    return crop


def _project_to_128(vector: np.ndarray) -> np.ndarray:
    vector = np.ravel(vector).astype(np.float32)
    if vector.size == 128:
        return vector
    if vector.size > 128:
        return np.asarray([chunk.mean() for chunk in np.array_split(vector, 128)], dtype=np.float32)
    return np.pad(vector, (0, 128 - vector.size), mode="constant")


def _normalize_embedding(vector: np.ndarray) -> list[float]:
    vector = vector.astype(np.float32)
    norm = float(np.linalg.norm(vector))
    if norm == 0:
        raise FaceServiceError("Face embedding is empty")
    return (vector / norm).tolist()


def _extract_landmark_features(image_bgr: np.ndarray) -> np.ndarray:
    result = _get_face_landmarker().detect(_to_mp_image(image_bgr))
    faces = result.face_landmarks or []
    if len(faces) != 1:
        raise FaceServiceError("Expected exactly one face")

    transformation = None
    if result.facial_transformation_matrixes:
        transformation = result.facial_transformation_matrixes[0]

    features = np.asarray(extract_features(faces[0], transformation), dtype=np.float32)
    if features.size != FEATURE_SIZE:
        raise FaceServiceError("Unexpected face feature size")

    _, _, scaler = _get_classifier_bundle()
    if scaler is not None:
        features = np.asarray(scaler.transform(features.reshape(1, -1))[0], dtype=np.float32)
    return features


def _predict_identity(features: np.ndarray) -> tuple[str | None, float]:
    classifier_model, label_encoder, _ = _get_classifier_bundle()
    if classifier_model is None or label_encoder is None:
        return None, 0.0

    batch = np.asarray(features, dtype=np.float32).reshape(1, -1)
    probabilities = classifier_model.predict(batch, verbose=0)[0]
    best_index = int(np.argmax(probabilities))
    confidence = float(probabilities[best_index])
    if confidence < FACE_CLASSIFIER_THRESHOLD:
        return None, confidence

    predicted_label = str(label_encoder.inverse_transform([best_index])[0])
    return predicted_label, confidence


def verify_face_quality(image_bytes: bytes) -> dict:
    """Validate that an uploaded registration image contains one clear frontal face."""
    try:
        image_bgr = _decode_image(image_bytes)
    except FaceServiceError as exc:
        return {"valid": False, "message": str(exc), "confidence": 0.0}

    boxes, confidences = _detect_faces(image_bgr)
    if len(boxes) != 1:
        message = "No face detected" if not boxes else "Multiple faces detected"
        return {"valid": False, "message": message, "confidence": max(confidences, default=0.0)}

    image_height, image_width = image_bgr.shape[:2]
    face_box = boxes[0]
    confidence = confidences[0] if confidences else 0.0
    width_ratio = face_box.width / image_width
    height_ratio = face_box.height / image_height
    if width_ratio < MIN_FACE_WIDTH_RATIO or height_ratio < MIN_FACE_HEIGHT_RATIO:
        return {
            "valid": False,
            "message": "Face is too small. Move closer to the camera.",
            "confidence": confidence,
        }

    face_crop = image_bgr[face_box.y_min : face_box.y_max, face_box.x_min : face_box.x_max]
    blur_score = _blur_variance(face_crop)
    if blur_score < MIN_BLUR_VARIANCE:
        return {
            "valid": False,
            "message": "Face image is blurry. Retake a clearer photo.",
            "confidence": confidence,
        }

    if not _is_frontal_face(image_bgr):
        return {
            "valid": False,
            "message": "Face must look forward toward the camera.",
            "confidence": confidence,
        }

    quality_confidence = min(confidence * 0.7 + min(blur_score / 300.0, 1.0) * 0.3, 1.0)
    return {
        "valid": True,
        "message": "Face image is valid",
        "confidence": round(float(quality_confidence), 4),
    }


def extract_embedding(image_bytes: bytes) -> list[float]:
    """Extract the trained 1447-dimensional landmark feature vector for one face image."""
    image_bgr = _decode_image(image_bytes)
    features = _extract_landmark_features(image_bgr)
    return [round(float(value), 8) for value in features.tolist()]


def compare_faces(embedding1: list[float], embedding2: list[float]) -> dict:
    """Compare two face embeddings with cosine similarity."""
    vector1 = np.asarray(embedding1, dtype=np.float32)
    vector2 = np.asarray(embedding2, dtype=np.float32)
    if vector1.shape != vector2.shape or vector1.size == 0:
        return {"match": False, "similarity": 0.0}

    denominator = float(np.linalg.norm(vector1) * np.linalg.norm(vector2))
    if denominator == 0:
        return {"match": False, "similarity": 0.0}

    similarity = float(np.dot(vector1, vector2) / denominator)
    similarity = max(min(similarity, 1.0), -1.0)
    return {
        "match": similarity >= FACE_MATCH_THRESHOLD,
        "similarity": round(similarity, 6),
    }


async def identify_employee(image_bytes: bytes, db: AsyncSession) -> dict | None:
    """Identify the active employee whose stored embedding best matches the image."""
    try:
        image_bgr = _decode_image(image_bytes)
        features = _extract_landmark_features(image_bgr)
    except FaceServiceError:
        return None

    embedding = [round(float(value), 8) for value in features.tolist()]

    # ── Path 1: Compare against stored embeddings ──
    result = await db.execute(
        select(Employee).where(
            Employee.status == "active",
            Employee.face_embedding.is_not(None),
        )
    )
    employees = result.scalars().all()

    best_employee: Employee | None = None
    best_similarity = 0.0
    for employee in employees:
        if not employee.face_embedding:
            continue
        comparison = compare_faces(embedding, employee.face_embedding)
        similarity = comparison["similarity"]
        if similarity > best_similarity:
            best_similarity = similarity
            best_employee = employee

    if best_employee is not None and best_similarity >= FACE_MATCH_THRESHOLD:
        return {
            "employee_id": best_employee.id,
            "name": best_employee.name,
            "similarity": round(best_similarity, 6),
        }

    # ── Path 2: Fallback to trained classifier model ──
    predicted_label, confidence = _predict_identity(features)
    if predicted_label is not None and confidence >= FACE_CLASSIFIER_THRESHOLD:
        display_name = " ".join(predicted_label.replace("_", " ").split()).strip()
        matched = await db.scalar(
            select(Employee).where(
                Employee.status == "active",
                Employee.name == display_name,
            )
        )
        if matched is not None:
            return {
                "employee_id": matched.id,
                "name": matched.name,
                "similarity": round(confidence, 6),
            }

    return None


def _normalize_name(value: str) -> str:
    return "_".join(value.strip().split()).lower()


async def register_face(image_bytes: bytes, employee_id: int, db: AsyncSession) -> dict:
    """Validate and store a face image and embedding on an employee record."""
    quality = verify_face_quality(image_bytes)
    if not quality["valid"]:
        return {"success": False, "message": quality["message"]}

    employee = await db.get(Employee, employee_id)
    if employee is None:
        return {"success": False, "message": "Employee not found"}

    embedding = extract_embedding(image_bytes)
    FACE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    image_path = FACE_STORAGE_DIR / f"{employee_id}.jpg"

    image_bgr = _decode_image(image_bytes)
    if not cv2.imwrite(str(image_path), image_bgr):
        return {"success": False, "message": "Failed to save face image"}

    employee.face_embedding = embedding
    employee.face_image_path = str(image_path)
    await db.commit()
    await db.refresh(employee)

    return {
        "success": True,
        "message": "Face registered successfully",
        "data": {
            "employee_id": employee.id,
            "face_image_path": employee.face_image_path,
            "confidence": quality["confidence"],
        },
    }
