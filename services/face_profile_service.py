"""Face-profile enrollment and matching helpers.

The existing classifier still works for the original trained classes. This
module adds employee-specific profiles so HR can enroll a new employee from a
few face samples without retraining the classifier.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable

import numpy as np
from sqlalchemy import func, select

from database.models import (
    Employee,
    EnrollmentSample,
    EnrollmentSession,
    FaceProfile,
)
from database.session import get_db_session

BASE_DIR = Path(__file__).resolve().parents[1]
STORAGE_DIR = Path(os.getenv("FACE_PROFILE_STORAGE_DIR", BASE_DIR / "storage" / "face_profiles"))
SAMPLE_STORAGE_DIR = Path(
    os.getenv("FACE_SAMPLE_STORAGE_DIR", BASE_DIR / "storage" / "enrollment_samples")
)
FACE_PROFILE_MATCH_THRESHOLD = float(os.getenv("FACE_PROFILE_MATCH_THRESHOLD", "0.80"))
PROFILE_MODEL_NAME = "mediapipe_landmark_profile"
PROFILE_MODEL_VERSION = "v1"


@dataclass(frozen=True)
class FaceProfileCandidate:
    profile_id: int
    employee_id: int
    employee_code: str
    full_name: str
    feature_dim: int
    centroid: np.ndarray
    sample_count: int
    quality_score: float | None


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))


def compare_feature_to_profile(feature: Iterable[float], centroid: Iterable[float]) -> float:
    """Return cosine similarity for a live feature vector and saved centroid."""
    return _cosine_similarity(
        np.asarray(list(feature), dtype=np.float32),
        np.asarray(list(centroid), dtype=np.float32),
    )


def find_best_profile_match(
    feature: Iterable[float],
    candidates: list[FaceProfileCandidate],
    threshold: float = FACE_PROFILE_MATCH_THRESHOLD,
) -> dict | None:
    """Find the best active employee profile above the configured threshold."""
    feature_array = np.asarray(list(feature), dtype=np.float32)
    best: FaceProfileCandidate | None = None
    best_similarity = 0.0

    for candidate in candidates:
        if candidate.feature_dim != feature_array.size:
            continue
        similarity = _cosine_similarity(feature_array, candidate.centroid)
        if similarity > best_similarity:
            best = candidate
            best_similarity = similarity

    if best is None or best_similarity < threshold:
        return None

    return {
        "profile_id": best.profile_id,
        "employee_id": best.employee_id,
        "employee_code": best.employee_code,
        "name": best.full_name,
        "similarity": best_similarity,
        "sample_count": best.sample_count,
        "quality_score": best.quality_score,
    }


def _artifact_path(employee_id: int, profile_version: int) -> Path:
    return STORAGE_DIR / f"employee_{employee_id}_v{profile_version}.json"


def _sample_path(employee_id: int, session_id: int, sample_index: int) -> Path:
    return SAMPLE_STORAGE_DIR / str(employee_id) / str(session_id) / f"sample_{sample_index:03d}.jpg"


def _artifact_uri(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def _resolve_artifact(uri: str) -> Path:
    path = Path(uri)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def load_active_face_profiles() -> list[FaceProfileCandidate]:
    """Load active profile centroids from profile artifacts."""
    with get_db_session() as session:
        rows = session.execute(
            select(FaceProfile, Employee)
            .join(Employee, Employee.id == FaceProfile.employee_id)
            .where(
                FaceProfile.profile_status == "ACTIVE",
                Employee.is_active.is_(True),
                Employee.employment_status == "ACTIVE",
            )
            .order_by(Employee.full_name.asc(), FaceProfile.profile_version.desc())
        ).all()

    candidates: list[FaceProfileCandidate] = []
    for profile, employee in rows:
        artifact_path = _resolve_artifact(profile.artifact_uri)
        if not artifact_path.exists():
            continue
        with artifact_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        centroid = np.asarray(payload.get("centroid", []), dtype=np.float32)
        if centroid.size != profile.feature_dim:
            continue
        quality_score = float(profile.quality_score) if profile.quality_score is not None else None
        candidates.append(
            FaceProfileCandidate(
                profile_id=profile.id,
                employee_id=employee.id,
                employee_code=employee.employee_code,
                full_name=employee.full_name,
                feature_dim=profile.feature_dim,
                centroid=centroid,
                sample_count=profile.sample_count,
                quality_score=quality_score,
            )
        )
    return candidates


def create_face_profile(
    *,
    employee_id: int,
    vectors: list[list[float]],
    quality_scores: list[float],
    sample_images: list[bytes],
    initiated_by: int | None = None,
    capture_device: str | None = None,
) -> dict:
    """Create a new active profile version and archive any previous versions."""
    if not vectors:
        raise ValueError("At least one accepted face sample is required")

    vector_array = np.asarray(vectors, dtype=np.float32)
    if vector_array.ndim != 2:
        raise ValueError("Face sample vectors must be a two-dimensional array")

    feature_dim = int(vector_array.shape[1])
    centroid = vector_array.mean(axis=0)
    quality_score = float(np.mean(quality_scores)) if quality_scores else None
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    with get_db_session() as session:
        employee = session.get(Employee, employee_id)
        if employee is None:
            raise ValueError("Employee not found")
        if not employee.is_active or employee.employment_status != "ACTIVE":
            raise ValueError("Employee must be active before face enrollment")

        current_version = session.scalar(
            select(func.max(FaceProfile.profile_version)).where(FaceProfile.employee_id == employee_id)
        )
        profile_version = int(current_version or 0) + 1

        for old_profile in session.scalars(
            select(FaceProfile).where(
                FaceProfile.employee_id == employee_id,
                FaceProfile.profile_status == "ACTIVE",
            )
        ):
            old_profile.profile_status = "ARCHIVED"

        enrollment_session = EnrollmentSession(
            employee_id=employee_id,
            initiated_by=initiated_by,
            capture_device=capture_device,
            required_samples=len(sample_images),
            collected_samples=len(sample_images),
            accepted_samples=len(vectors),
            rejected_samples=max(len(sample_images) - len(vectors), 0),
            session_status="COMPLETED",
            completed_at=datetime.now(),
            notes="Created from uploaded face samples",
        )
        session.add(enrollment_session)
        session.flush()

        artifact_path = _artifact_path(employee_id, profile_version)
        profile = FaceProfile(
            employee_id=employee_id,
            profile_version=profile_version,
            model_name=PROFILE_MODEL_NAME,
            model_version=PROFILE_MODEL_VERSION,
            feature_dim=feature_dim,
            artifact_uri=_artifact_uri(artifact_path),
            quality_score=Decimal(str(round(quality_score, 2))) if quality_score is not None else None,
            sample_count=len(vectors),
            profile_status="ACTIVE",
            trained_at=datetime.now(),
        )
        session.add(profile)
        session.flush()

        for index, image_bytes in enumerate(sample_images, start=1):
            sample_path = _sample_path(employee_id, enrollment_session.id, index)
            sample_path.parent.mkdir(parents=True, exist_ok=True)
            with sample_path.open("wb") as f:
                f.write(image_bytes)
            session.add(
                EnrollmentSample(
                    enrollment_session_id=enrollment_session.id,
                    employee_id=employee_id,
                    file_uri=_artifact_uri(sample_path),
                    zone_label="uploaded",
                    quality_score=(
                        Decimal(str(round(quality_scores[index - 1], 2)))
                        if index - 1 < len(quality_scores)
                        else None
                    ),
                    is_accepted=index <= len(vectors),
                )
            )

        payload = {
            "schema_version": 1,
            "employee_id": employee_id,
            "employee_code": employee.employee_code,
            "full_name": employee.full_name,
            "profile_id": profile.id,
            "profile_version": profile_version,
            "model_name": PROFILE_MODEL_NAME,
            "model_version": PROFILE_MODEL_VERSION,
            "feature_dim": feature_dim,
            "sample_count": len(vectors),
            "quality_score": quality_score,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "centroid": centroid.astype(float).tolist(),
        }
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = artifact_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f)
        shutil.move(str(tmp_path), artifact_path)

        employee.face_enrollment_status = "ENROLLED"
        session.flush()

        return {
            "profile_id": profile.id,
            "employee_id": employee.id,
            "employee_code": employee.employee_code,
            "full_name": employee.full_name,
            "profile_version": profile.profile_version,
            "sample_count": profile.sample_count,
            "quality_score": quality_score,
            "artifact_uri": profile.artifact_uri,
        }
