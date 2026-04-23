# setup.py — Download required MediaPipe model
# Run once: python setup.py
import urllib.request, os

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, 'models')
MODEL_PATH = os.path.join(MODELS_DIR, 'face_landmarker.task')
MODEL_URL  = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
)

os.makedirs(MODELS_DIR, exist_ok=True)

if os.path.exists(MODEL_PATH):
    print(f"[OK] face_landmarker.task already exists.")
else:
    print("Downloading face_landmarker.task (~6 MB)...")
    def progress(b, bs, total):
        pct = min(b * bs / total * 100, 100)
        print(f"\r  {pct:.1f}%", end="", flush=True)
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH, progress)
    print(f"\n[SAVED] {MODEL_PATH}")

print("\nSetup complete. Now run:\n  python src/collect.py")