"""Face quality, embedding, matching, and employee identification service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

import cv2
import mediapipe as mp
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tensorflow.keras.applications.mobilenet_v2 import MobileNetV2, preprocess_input
from tensorflow.keras.models import Model, load_model

from app.models.employee import Employee


FACE_MATCH_THRESHOLD = 0.75
MIN_FACE_WIDTH_RATIO = 0.18
MIN_FACE_HEIGHT_RATIO = 0.18
MIN_BLUR_VARIANCE = 80.0
FACE_STORAGE_DIR = Path(os.getenv("FACE_STORAGE_DIR", "storage/faces"))
FACE_EMBEDDING_MODEL_PATH = os.getenv("FACE_EMBEDDING_MODEL_PATH")


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


_face_detection: mp.solutions.face_detection.FaceDetection | None = None
_face_mesh: mp.solutions.face_mesh.FaceMesh | None = None
_embedding_model: Model | None = None


def _get_face_detection() -> mp.solutions.face_detection.FaceDetection:
    global _face_detection
    if _face_detection is None:
        _face_detection = mp.solutions.face_detection.FaceDetection(
            model_selection=1,
            min_detection_confidence=0.55,
        )
    return _face_detection


def _get_face_mesh() -> mp.solutions.face_mesh.FaceMesh:
    global _face_mesh
    if _face_mesh is None:
        _face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=2,
            refine_landmarks=True,
            min_detection_confidence=0.55,
        )
    return _face_mesh


def _get_embedding_model() -> Model:
    global _embedding_model
    if _embedding_model is None:
        if FACE_EMBEDDING_MODEL_PATH and Path(FACE_EMBEDDING_MODEL_PATH).exists():
            _embedding_model = load_model(FACE_EMBEDDING_MODEL_PATH, compile=False)
        else:
            base_model = MobileNetV2(
                include_top=False,
                weights=None,
                pooling="avg",
                input_shape=(160, 160, 3),
            )
            _embedding_model = Model(inputs=base_model.input, outputs=base_model.output)
    return _embedding_model


def _decode_image(image_bytes: bytes) -> np.ndarray:
    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise FaceServiceError("Invalid image file")
    return image


def _detect_faces(image_bgr: np.ndarray) -> tuple[list[FaceBox], list[float]]:
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    height, width = image_bgr.shape[:2]
    result = _get_face_detection().process(image_rgb)
    if not result.detections:
        return [], []

    boxes: list[FaceBox] = []
    confidences: list[float] = []
    for detection in result.detections:
        location = detection.location_data.relative_bounding_box
        x_min = max(int(location.xmin * width), 0)
        y_min = max(int(location.ymin * height), 0)
        x_max = min(int((location.xmin + location.width) * width), width)
        y_max = min(int((location.ymin + location.height) * height), height)
        boxes.append(FaceBox(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max))
        confidences.append(float(detection.score[0]) if detection.score else 0.0)
    return boxes, confidences


def _blur_variance(face_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _is_frontal_face(image_bgr: np.ndarray) -> bool:
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    result = _get_face_mesh().process(image_rgb)
    if not result.multi_face_landmarks or len(result.multi_face_landmarks) != 1:
        return False

    landmarks = result.multi_face_landmarks[0].landmark
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
    """Extract a deterministic 128-dimensional face embedding from one face image."""
    image_bgr = _decode_image(image_bytes)
    face_crop = _largest_face_crop(image_bgr)
    face_rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(face_rgb, (160, 160), interpolation=cv2.INTER_AREA)
    batch = np.expand_dims(resized.astype(np.float32), axis=0)
    features = _get_embedding_model().predict(preprocess_input(batch), verbose=0)[0]
    folded = _project_to_128(features)
    return [round(float(value), 8) for value in _normalize_embedding(folded)]


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
    embedding = extract_embedding(image_bytes)
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

    if best_employee is None or best_similarity < FACE_MATCH_THRESHOLD:
        return None

    return {
        "employee_id": best_employee.id,
        "name": best_employee.name,
        "similarity": round(best_similarity, 6),
    }


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
