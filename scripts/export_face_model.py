"""Export the face recognition model and runtime artifacts as a deployable bundle.

Run from project root:
    python scripts/export_face_model.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import shutil
from datetime import datetime, timezone
from pathlib import Path

import tensorflow as tf
from tensorflow.keras.models import load_model


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MODELS_DIR = BASE_DIR / "models"
DEFAULT_OUTPUT_DIR = BASE_DIR / "exports" / "face-model"
REQUIRED_ARTIFACTS = {
    "keras_h5": "face_model.h5",
    "label_encoder": "label_encoder.pkl",
    "scaler": "scaler.pkl",
    "mediapipe_task": "face_landmarker.task",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_required_artifacts(models_dir: Path, output_dir: Path) -> dict[str, dict[str, str | int]]:
    copied: dict[str, dict[str, str | int]] = {}
    for artifact_key, filename in REQUIRED_ARTIFACTS.items():
        source = models_dir / filename
        if not source.exists():
            raise FileNotFoundError(f"Missing required artifact: {source}")
        target = output_dir / filename
        shutil.copy2(source, target)
        copied[artifact_key] = {
            "file": filename,
            "bytes": target.stat().st_size,
            "sha256": sha256_file(target),
        }
    return copied


def export_tensorflow_formats(models_dir: Path, output_dir: Path) -> dict[str, dict]:
    model = load_model(models_dir / "face_model.h5", compile=False)
    exported: dict[str, dict] = {}

    keras_path = output_dir / "face_model.keras"
    model.save(keras_path)
    exported["keras_v3"] = {
        "file": keras_path.name,
        "bytes": keras_path.stat().st_size,
        "sha256": sha256_file(keras_path),
    }

    try:
        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        tflite_model = converter.convert()
        tflite_path = output_dir / "face_model.tflite"
        tflite_path.write_bytes(tflite_model)
        exported["tflite"] = {
            "file": tflite_path.name,
            "bytes": tflite_path.stat().st_size,
            "sha256": sha256_file(tflite_path),
        }
    except Exception as exc:
        exported["tflite_error"] = {
            "file": "",
            "bytes": 0,
            "sha256": "",
            "error": str(exc),
        }

    return exported


def load_metadata(models_dir: Path) -> dict:
    with (models_dir / "label_encoder.pkl").open("rb") as handle:
        label_encoder = pickle.load(handle)
    with (models_dir / "scaler.pkl").open("rb") as handle:
        scaler = pickle.load(handle)
    model = load_model(models_dir / "face_model.h5", compile=False)

    return {
        "classes": [str(item) for item in label_encoder.classes_],
        "input_shape": list(model.input_shape),
        "output_shape": list(model.output_shape),
        "feature_size": int(getattr(scaler, "n_features_in_", model.input_shape[-1])),
        "preprocessing": [
            "BGR frame",
            "horizontal mirror",
            "CLAHE LAB luminance enhancement",
            "MediaPipe FaceLandmarker with transformation matrix",
            "utils.features.extract_features",
            "StandardScaler.transform",
            "Keras softmax model",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    models_dir = args.models_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts = copy_required_artifacts(models_dir, output_dir)
    artifacts.update(export_tensorflow_formats(models_dir, output_dir))
    metadata = load_metadata(models_dir)

    manifest = {
        "name": "attendance-face-recognition",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runtime": "MediaPipe FaceLandmarker + TensorFlow/Keras classifier",
        "artifacts": artifacts,
        **metadata,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Exported face model bundle to: {output_dir}")
    print(f"Classes: {', '.join(metadata['classes'])}")
    print(f"Feature size: {metadata['feature_size']}")


if __name__ == "__main__":
    main()
