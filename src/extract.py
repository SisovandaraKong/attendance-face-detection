# src/extract.py — Extract rich landmark features from dataset
# Features: x, y, z per landmark + 10 key distances + 3 head angles
# Run from project root: python src/extract.py

import cv2
import os
import pickle
import sys

import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

# Shared feature extractor — must match training exactly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.features import extract_features

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(BASE_DIR, 'dataset')
OUTPUT_PKL = os.path.join(BASE_DIR, 'models', 'landmarks_data.pkl')
MODEL_FILE = os.path.join(BASE_DIR, 'models', 'face_landmarker.task')

os.makedirs(os.path.join(BASE_DIR, 'models'), exist_ok=True)

if not os.path.exists(MODEL_FILE):
    print("[ERROR] face_landmarker.task not found. Run: python setup.py")
    exit()

# ── MediaPipe static image mode for extraction ────────────
base_options = mp_python.BaseOptions(model_asset_path=MODEL_FILE)
options = vision.FaceLandmarkerOptions(
    base_options=base_options,
    num_faces=1,
    min_face_detection_confidence=0.2,
    min_face_presence_confidence=0.2,
    min_tracking_confidence=0.2,
    output_face_blendshapes=False,
    output_facial_transformation_matrixes=True,
)
detector = vision.FaceLandmarker.create_from_options(options)




# ── CLAHE for low-light images ────────────────────────────
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

data          = []
labels        = []
total_success = 0
total_fail    = 0

persons = sorted([
    d for d in os.listdir(DATA_DIR)
    if os.path.isdir(os.path.join(DATA_DIR, d))
])

if not persons:
    print("[ERROR] No persons found. Run src/collect.py first.")
    exit()

print("=" * 56)
print("  Face Attendance — Step 2: Extract Features")
print("=" * 56)
print(f"\n  Found {len(persons)} persons\n")

for person in persons:
    folder_path = os.path.join(DATA_DIR, person)
    img_files   = sorted([
        f for f in os.listdir(folder_path)
        if f.lower().endswith(('.jpg', '.png', '.jpeg'))
    ])

    ok = fail = 0

    for img_file in img_files:
        img_bgr = cv2.imread(os.path.join(folder_path, img_file))
        if img_bgr is None:
            fail += 1
            continue

        # Enhance low-light images
        lab      = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
        l, a, b  = cv2.split(lab)
        lab2     = cv2.merge([clahe.apply(l), a, b])
        enhanced = cv2.cvtColor(lab2, cv2.COLOR_LAB2BGR)

        img_rgb  = cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
        result   = detector.detect(mp_image)

        if result.face_landmarks and len(result.face_landmarks) > 0:
            matrix = (result.facial_transformation_matrixes[0]
                      if result.facial_transformation_matrixes else None)
            feats  = extract_features(result.face_landmarks[0], matrix)
            data.append(feats)
            labels.append(person)
            ok += 1
            total_success += 1
        else:
            fail += 1
            total_fail  += 1

    status = f"  ({fail} failed)" if fail else ""
    print(f"  {person.replace('_',' '):<28}  {ok}/{len(img_files)} extracted{status}")

if total_success == 0:
    print("\n[ERROR] No features extracted. Check dataset.")
    detector.close()
    exit()

with open(OUTPUT_PKL, 'wb') as f:
    pickle.dump({'data': data, 'labels': labels}, f)

feat_size = len(data[0])
print(f"\n  Total extracted : {total_success}")
print(f"  Failed          : {total_fail}")
print(f"  Feature size    : {feat_size}  (478×3 coords + 10 distances + 3 angles)")
print(f"  Saved to        : {OUTPUT_PKL}")
print(f"\nNext: python src/train.py")

detector.close()