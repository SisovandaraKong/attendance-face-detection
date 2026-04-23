# src/webcam.py — Real-time face recognition attendance scanner (standalone)
# Features: CLAHE low-light fix, 15-frame rolling prediction buffer,
#           StandardScaler, head pose angles, rich feature vector
# Run from project root: python src/webcam.py

import csv
import math
import os
import pickle
import sys
import time
from collections import deque
from datetime import datetime

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from tensorflow.keras.models import load_model as keras_load_model

# Shared utilities — single source of truth for feature extraction and drawing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.features import extract_features
from utils.drawing import draw_landmarks, draw_face_box

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_H5    = os.path.join(BASE_DIR, 'models', 'face_model.h5')
ENCODER_PKL = os.path.join(BASE_DIR, 'models', 'label_encoder.pkl')
SCALER_PKL  = os.path.join(BASE_DIR, 'models', 'scaler.pkl')
MODEL_FILE  = os.path.join(BASE_DIR, 'models', 'face_landmarker.task')
LOGS_DIR    = os.path.join(BASE_DIR, 'logs')

CONFIDENCE_THRESHOLD = 0.92   # must be ≥ 92% confident (averaged over buffer)
RECOGNITION_COOLDOWN = 3      # seconds before logging same person again
BUFFER_SIZE          = 15     # frames to average predictions over

os.makedirs(LOGS_DIR, exist_ok=True)

for path, hint in [
    (MODEL_H5,    "Run src/train.py first"),
    (ENCODER_PKL, "Run src/train.py first"),
    (SCALER_PKL,  "Run src/train.py first"),
    (MODEL_FILE,  "Run python setup.py first"),
]:
    if not os.path.exists(path):
        print(f"[ERROR] Missing: {os.path.basename(path)}  → {hint}")
        exit()

# ── Load model + encoder + scaler ────────────────────────
keras_model = keras_load_model(MODEL_H5, compile=False)
with open(ENCODER_PKL, 'rb') as f: le     = pickle.load(f)
with open(SCALER_PKL,  'rb') as f: scaler = pickle.load(f)

print("=" * 56)
print("  Face Attendance — Step 4: Live Scanner")
print("=" * 56)
print(f"\n  Known persons ({len(le.classes_)}):")
for i, n in enumerate(le.classes_):
    print(f"    [{i}] {n.replace('_', ' ')}")
print("\n  Q = quit  |  S = screenshot\n")

# ── MediaPipe ─────────────────────────────────────────────
base_options = mp_python.BaseOptions(model_asset_path=MODEL_FILE)
options = vision.FaceLandmarkerOptions(
    base_options=base_options,
    num_faces=1,
    min_face_detection_confidence=0.3,
    min_face_presence_confidence=0.3,
    min_tracking_confidence=0.3,
    output_face_blendshapes=False,
    output_facial_transformation_matrixes=True,
)
detector = vision.FaceLandmarker.create_from_options(options)

# ── extract_features and draw_landmarks come from utils/ ─────
# (imported at the top of this file — do not add local copies here)

# ── Attendance log ────────────────────────────────────────
today    = datetime.now().strftime("%Y-%m-%d")
log_file = os.path.join(LOGS_DIR, f'attendance_{today}.csv')

def write_log(name):
    header = not os.path.exists(log_file)
    with open(log_file, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['Name','Date','Time','Status'])
        if header: w.writeheader()
        w.writerow({'Name': name.replace('_',' '), 'Date': today,
                    'Time': datetime.now().strftime('%H:%M:%S'), 'Status': 'Present'})

def load_log():
    if not os.path.exists(log_file): return []
    with open(log_file) as f: return list(csv.DictReader(f))

# ── CLAHE for low-light ───────────────────────────────────
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))

# ── Rolling prediction buffer (temporal smoothing) ────────
# Averages predictions over BUFFER_SIZE frames → far fewer false readings
pred_buffer = deque(maxlen=BUFFER_SIZE)

# ── Webcam ────────────────────────────────────────────────
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

last_logged = {}
log_entries = load_log()
fps         = 0.0
prev_time   = time.time()

while True:
    ret, frame = cap.read()
    if not ret: break

    frame = cv2.flip(frame, 1)
    h, w  = frame.shape[:2]

    now       = time.time()
    fps       = 0.9 * fps + 0.1 / max(now - prev_time, 1e-5)
    prev_time = now

    # ── CLAHE low-light enhancement ──────────────────────
    lab         = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b_ch  = cv2.split(lab)
    lab2        = cv2.merge([clahe.apply(l), a, b_ch])
    enhanced    = cv2.cvtColor(lab2, cv2.COLOR_LAB2BGR)

    rgb      = cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result   = detector.detect(mp_image)

    face_found = (result.face_landmarks is not None
                  and len(result.face_landmarks) > 0)

    name_label = "Unknown"
    confidence = 0.0

    if face_found:
        face_lm = result.face_landmarks[0]
        matrix  = (result.facial_transformation_matrixes[0]
                   if result.facial_transformation_matrixes else None)

        # Draw landmarks + get pixel coordinates
        pts = draw_landmarks(enhanced, face_lm)

        # Extract features + scale
        feats        = extract_features(face_lm, matrix)
        feats_scaled = scaler.transform(np.array([feats], dtype=np.float32))

        # Predict
        pred = keras_model.predict(feats_scaled, verbose=0)[0]
        pred_buffer.append(pred)

        # Average over buffer for stable prediction
        avg_pred   = np.mean(pred_buffer, axis=0)
        label_id   = int(np.argmax(avg_pred))
        confidence = float(avg_pred[label_id])

        if confidence >= CONFIDENCE_THRESHOLD:
            name_label = le.classes_[label_id].replace('_', ' ')
            box_color  = (0, 255, 80)
        else:
            name_label = "Unknown"
            box_color  = (0, 80, 255)
            pred_buffer.clear()   # reset buffer when unknown

        draw_face_box(enhanced, pts, name_label, confidence, box_color)

        # Log attendance
        if confidence >= CONFIDENCE_THRESHOLD:
            key = le.classes_[label_id]
            if key not in last_logged or (now - last_logged[key]) >= RECOGNITION_COOLDOWN:
                write_log(key)
                last_logged[key] = now
                log_entries = load_log()
                print(f"[LOG] {name_label}  {datetime.now().strftime('%H:%M:%S')}")
    else:
        pred_buffer.clear()   # reset when face leaves frame

    # ── Top bar ───────────────────────────────────────────
    cv2.rectangle(enhanced, (0, 0), (w, 55), (15, 15, 20), -1)
    cv2.putText(enhanced, 'FACE RECOGNITION ATTENDANCE SYSTEM',
                (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 255), 2)
    cv2.putText(enhanced, datetime.now().strftime('%H:%M:%S'),
                (12, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (140, 140, 140), 1)
    cv2.putText(enhanced, f'FPS: {fps:.0f}',
                (w - 110, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 80), 1)
    cv2.putText(enhanced, f'Known: {len(le.classes_)}',
                (w - 110, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 140, 140), 1)

    # ── Attendance side panel ─────────────────────────────
    panel_w = 260
    panel   = np.full((h, panel_w, 3), (16, 16, 20), dtype=np.uint8)
    cv2.rectangle(panel, (0, 0), (panel_w, 50), (28, 28, 36), -1)
    cv2.putText(panel, 'ATTENDANCE TODAY', (10, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 1)
    cv2.putText(panel, datetime.now().strftime('%d %b %Y'), (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (110, 110, 110), 1)
    cv2.putText(panel, str(len(log_entries)), (panel_w - 38, 34),
                cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 220, 80), 2)
    cv2.line(panel, (10, 54), (panel_w - 10, 54), (45, 45, 52), 1)

    y = 74
    for entry in reversed(log_entries[-18:]):
        cv2.putText(panel, entry.get('Name',''), (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, (225, 225, 225), 1)
        cv2.putText(panel, entry.get('Time',''), (10, y + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.37, (100, 100, 100), 1)
        cv2.line(panel, (10, y + 25), (panel_w - 10, y + 25), (32, 32, 38), 1)
        y += 38
        if y > h - 20: break

    composite = np.hstack([enhanced, panel])
    cv2.putText(composite, 'Q: Quit   S: Screenshot',
                (12, composite.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (70, 70, 70), 1)

    cv2.imshow('Face Attendance System', composite)
    key = cv2.waitKey(1) & 0xFF
    if key in (ord('q'), 27): break
    elif key == ord('s'):
        fname = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        cv2.imwrite(fname, composite)
        print(f"[SAVED] {fname}")

cap.release()
cv2.destroyAllWindows()
detector.close()

entries = load_log()
print(f"\n{'─'*44}")
print(f"  Present today: {len(entries)}")
for e in entries:
    print(f"  • {e['Name']:<26} {e['Time']}")
print(f"{'─'*44}\n")