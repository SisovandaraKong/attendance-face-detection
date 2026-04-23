# src/collect.py — Face ID-style dataset collector
# Guides you through 7 pose zones (front, left, right, up, down, near, far)
# so the model learns your face from every angle and distance.
#
# Run from project root: python src/collect.py
# SPACE = start/pause  |  N = next zone / back to menu  |  Q = quit

import cv2, os, time, math
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(BASE_DIR, 'dataset')
MODEL_FILE = os.path.join(BASE_DIR, 'models', 'face_landmarker.task')

# Images per ZONE (7 zones × 30 = 210 images per person)
IMAGES_PER_ZONE = 30

# ── Pose zones — tells user what to do ───────────────────
ZONES = [
    {"name": "Front",       "instruction": "Look straight at camera",           "icon": "◉"},
    {"name": "Turn Left",   "instruction": "Slowly turn your head LEFT",         "icon": "←"},
    {"name": "Turn Right",  "instruction": "Slowly turn your head RIGHT",        "icon": "→"},
    {"name": "Tilt Up",     "instruction": "Tilt your face UP slightly",         "icon": "↑"},
    {"name": "Tilt Down",   "instruction": "Tilt your face DOWN slightly",       "icon": "↓"},
    {"name": "Move Close",  "instruction": "Move CLOSER to camera (fill frame)", "icon": "⊕"},
    {"name": "Move Far",    "instruction": "Move FARTHER from camera",           "icon": "⊖"},
]

os.makedirs(DATA_DIR, exist_ok=True)

if not os.path.exists(MODEL_FILE):
    print("[ERROR] face_landmarker.task not found. Run: python setup.py")
    exit()

# ── MediaPipe — low threshold to catch side/far faces ────
base_options = mp_python.BaseOptions(model_asset_path=MODEL_FILE)
options = vision.FaceLandmarkerOptions(
    base_options=base_options,
    num_faces=1,
    min_face_detection_confidence=0.3,   # lower = detects at angle/distance
    min_face_presence_confidence=0.3,
    min_tracking_confidence=0.3,
    output_face_blendshapes=False,
    output_facial_transformation_matrixes=True,  # needed for pose check
)
detector = vision.FaceLandmarker.create_from_options(options)

# ── Landmark drawing ──────────────────────────────────────
FACE_OVAL = [
    (10,338),(338,297),(297,332),(332,284),(284,251),(251,389),(389,356),
    (356,454),(454,323),(323,361),(361,288),(288,397),(397,365),(365,379),
    (379,378),(378,400),(400,377),(377,152),(152,148),(148,176),(176,149),
    (149,150),(150,136),(136,172),(172,58),(58,132),(132,93),(93,234),
    (234,127),(127,162),(162,21),(21,54),(54,103),(103,67),(67,109),(109,10),
]
LEFT_EYE  = [(33,7),(7,163),(163,144),(144,145),(145,153),(153,154),(154,155),
             (155,133),(33,246),(246,161),(161,160),(160,159),(159,158),(158,157),(157,173),(173,133)]
RIGHT_EYE = [(362,382),(382,381),(381,380),(380,374),(374,373),(373,390),
             (390,249),(249,263),(362,398),(398,384),(384,385),(385,386),(386,387),(387,388),(388,466),(466,263)]
LIPS      = [(61,146),(146,91),(91,181),(181,84),(84,17),(17,314),(314,405),
             (405,321),(321,375),(375,291),(61,185),(185,40),(40,39),(39,37),
             (37,0),(0,267),(267,269),(269,270),(270,409),(409,291)]
NOSE      = [(168,6),(6,197),(197,195),(195,5),(5,4),(4,1),(1,19),(19,94),(94,2)]
ALL_CONN  = FACE_OVAL + LEFT_EYE + RIGHT_EYE + LIPS + NOSE

def draw_landmarks(frame, lms, color=(0, 220, 180)):
    h, w = frame.shape[:2]
    pts  = [(int(lm.x * w), int(lm.y * h)) for lm in lms]
    for a, b in ALL_CONN:
        if a < len(pts) and b < len(pts):
            cv2.line(frame, pts[a], pts[b], color, 1, cv2.LINE_AA)
    for x, y in pts:
        cv2.circle(frame, (x, y), 1, (0, 255, 210), -1, cv2.LINE_AA)

def augment_and_save(frame, path_base, idx):
    """
    Save the original + 4 augmented versions of each captured frame.
    This multiplies effective dataset size x5 and adds lighting/flip variety.
    """
    clean = frame.copy()

    # 1. Original
    cv2.imwrite(f"{path_base}_{idx:04d}_orig.jpg", clean)

    # 2. Brightness +30
    bright = cv2.convertScaleAbs(clean, alpha=1.0, beta=30)
    cv2.imwrite(f"{path_base}_{idx:04d}_bright.jpg", bright)

    # 3. Brightness -30 (simulates low light)
    dark = cv2.convertScaleAbs(clean, alpha=1.0, beta=-30)
    cv2.imwrite(f"{path_base}_{idx:04d}_dark.jpg", dark)

    # 4. Slight blur (simulates motion)
    blurred = cv2.GaussianBlur(clean, (3, 3), 0)
    cv2.imwrite(f"{path_base}_{idx:04d}_blur.jpg", blurred)

    # 5. Horizontal flip (mirror)
    flipped = cv2.flip(clean, 1)
    cv2.imwrite(f"{path_base}_{idx:04d}_flip.jpg", flipped)

    return 5   # returns how many files were saved

def draw_zone_guide(frame, zone, zone_idx, count, total_zones):
    """Draw zone instruction overlay on the frame."""
    h, w = frame.shape[:2]

    # Top bar
    cv2.rectangle(frame, (0, 0), (w, 90), (15, 15, 20), -1)

    # Zone progress dots
    dot_start = w // 2 - (total_zones * 22) // 2
    for i in range(total_zones):
        cx = dot_start + i * 22
        if i < zone_idx:
            cv2.circle(frame, (cx, 12), 5, (0, 200, 80), -1)    # done — green
        elif i == zone_idx:
            cv2.circle(frame, (cx, 12), 6, (0, 220, 255), -1)   # current — cyan
        else:
            cv2.circle(frame, (cx, 12), 5, (60, 60, 60), -1)    # future — grey

    # Zone name + instruction
    cv2.putText(frame, f"{zone['icon']}  {zone['name'].upper()}",
                (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 220, 255), 2)
    cv2.putText(frame, zone['instruction'],
                (15, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

    # Count on right
    cv2.putText(frame, f"{count}/{IMAGES_PER_ZONE}",
                (w - 110, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 130), 2)

    # Progress bar for this zone
    prog = int(w * min(count / IMAGES_PER_ZONE, 1.0))
    cv2.rectangle(frame, (0, 90), (prog, 98), (0, 200, 80), -1)
    cv2.rectangle(frame, (0, 90), (w, 98), (40, 40, 40), 1)


# ── Webcam ────────────────────────────────────────────────
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

# ── CLAHE for low-light enhancement ─────────────────────
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

print("=" * 56)
print("  Face ID Collector — Step 1: Data Collection")
print("=" * 56)

while True:
    print("\n  1. Add / continue collecting a person")
    print("  2. Show dataset summary")
    print("  3. Exit")
    choice = input("\n  Choice (1/2/3): ").strip()

    if choice == "2":
        persons = [d for d in os.listdir(DATA_DIR)
                   if os.path.isdir(os.path.join(DATA_DIR, d))]
        if not persons:
            print("  No data collected yet.")
        else:
            total_needed = IMAGES_PER_ZONE * len(ZONES) * 5  # ×5 augmentation
            print(f"\n  {'Person':<28}  Images  Status")
            print("  " + "─" * 48)
            for p in sorted(persons):
                cnt = len([f for f in os.listdir(os.path.join(DATA_DIR, p))
                           if f.lower().endswith(".jpg")])
                status = "✓ Complete" if cnt >= total_needed else f"⚠  {cnt}/{total_needed}"
                print(f"  {p.replace('_', ' '):<28}  {cnt:>6}  {status}")
        continue

    elif choice == "3":
        print("\n[INFO] Done. Run: python src/extract.py")
        break

    elif choice != "1":
        continue

    raw = input("  Full name (e.g. Sokha Chan): ").strip()
    if not raw:
        print("[ERROR] Name cannot be empty.")
        continue

    person_name = raw.replace(" ", "_")
    save_dir    = os.path.join(DATA_DIR, person_name)
    os.makedirs(save_dir, exist_ok=True)

    print(f'\n  Collecting for: "{raw}"')
    print(f"  You will go through {len(ZONES)} pose zones × {IMAGES_PER_ZONE} images each")
    print(f"  Each image is auto-augmented ×5 → {len(ZONES) * IMAGES_PER_ZONE * 5} total images")
    print(f"\n  SPACE = start/pause  |  N = skip zone  |  Q = quit\n")

    # ── Zone loop ─────────────────────────────────────────
    for zone_idx, zone in enumerate(ZONES):
        zone_prefix = os.path.join(save_dir, f"z{zone_idx}_{zone['name'].replace(' ','_')}")

        # Count already saved for this zone
        existing_zone = len([f for f in os.listdir(save_dir)
                             if f.startswith(f"z{zone_idx}_") and f.endswith("_orig.jpg")])
        count     = existing_zone
        capturing = False

        if count >= IMAGES_PER_ZONE:
            print(f"  [SKIP] Zone {zone_idx+1}/{len(ZONES)}: {zone['name']} — already done")
            continue

        print(f"\n  Zone {zone_idx+1}/{len(ZONES)}: {zone['name']}")
        print(f"  → {zone['instruction']}")
        print(f"  Press SPACE to start collecting this zone\n")

        frame_skip = 0

        while count < IMAGES_PER_ZONE:
            ret, frame = cap.read()
            if not ret:
                break

            frame      = cv2.flip(frame, 1)
            h, w       = frame.shape[:2]
            frame_skip += 1

            # ── Low-light enhancement ─────────────────────
            # Enhance brightness before detection AND saving
            lab       = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b   = cv2.split(lab)
            l_eq      = clahe.apply(l)
            lab_eq    = cv2.merge([l_eq, a, b])
            enhanced  = cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)

            # Run detection on enhanced frame
            rgb      = cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result   = detector.detect(mp_image)

            face_found = (result.face_landmarks is not None
                          and len(result.face_landmarks) > 0)

            # Draw landmarks on display copy
            display = enhanced.copy()
            if face_found:
                lm_color = (0, 255, 100) if capturing else (0, 200, 180)
                draw_landmarks(display, result.face_landmarks[0], color=lm_color)

            # ── Draw zone guide ───────────────────────────
            draw_zone_guide(display, zone, zone_idx, count, len(ZONES))

            # Status
            if not face_found:
                status_txt   = "No face detected"
                status_color = (0, 80, 255)
            elif capturing:
                status_txt   = "CAPTURING — move naturally"
                status_color = (0, 255, 100)
            else:
                status_txt   = "Ready — press SPACE to start"
                status_color = (160, 160, 160)

            cv2.putText(display, status_txt,
                        (15, h - 55), cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2)

            # Bottom bar
            cv2.rectangle(display, (0, h - 40), (w, h), (15, 15, 20), -1)
            cv2.putText(display, 'SPACE: start/pause   N: skip zone   Q: quit',
                        (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (130, 130, 130), 1)

            cv2.imshow('Face ID Collector', display)
            key = cv2.waitKey(30) & 0xFF

            if key == ord('q'):
                cap.release()
                cv2.destroyAllWindows()
                detector.close()
                print("Quit.")
                exit()
            elif key == ord('n'):
                print(f"  Skipped zone: {zone['name']} (saved {count})")
                break
            elif key == ord(' '):
                capturing = not capturing
                print("  CAPTURING..." if capturing else "  Paused")

            # Save every 3rd frame to avoid duplicates
            if capturing and face_found and frame_skip % 3 == 0:
                saved = augment_and_save(enhanced, zone_prefix, count)
                count += 1
                if count >= IMAGES_PER_ZONE:
                    print(f"  ✓ Zone {zone_idx+1} done: {zone['name']}")
                    break

        cv2.destroyAllWindows()

    # Count total
    total = len([f for f in os.listdir(save_dir) if f.lower().endswith(".jpg")])
    print(f"\n  Collection complete for {raw}!")
    print(f"  Total images saved: {total}")
    print(f"  Run next: python src/extract.py")

cap.release()
cv2.destroyAllWindows()
detector.close()
print("\nDone! Run: python src/extract.py")