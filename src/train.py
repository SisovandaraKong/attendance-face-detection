# src/train.py — Train face recognition model
# Run from project root: python src/train.py

import os, pickle
import numpy as np
from collections import Counter
from sklearn.model_selection import train_test_split
from sklearn.preprocessing   import LabelEncoder, StandardScaler
from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import classification_report
from tensorflow.keras.models    import Sequential
from tensorflow.keras.layers    import Dense, Dropout, BatchNormalization
from tensorflow.keras.regularizers import l2
from tensorflow.keras.utils     import to_categorical
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

BASE_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANDMARKS_PKL   = os.path.join(BASE_DIR, 'models', 'landmarks_data.pkl')
ENCODER_PKL     = os.path.join(BASE_DIR, 'models', 'label_encoder.pkl')
SCALER_PKL      = os.path.join(BASE_DIR, 'models', 'scaler.pkl')          # NEW
MODEL_SAVE_PATH = os.path.join(BASE_DIR, 'models', 'face_model.h5')

print("=" * 56)
print("  Face Attendance — Step 3: Training")
print("=" * 56)

if not os.path.exists(LANDMARKS_PKL):
    print("[ERROR] landmarks_data.pkl not found. Run src/extract.py first.")
    exit()

with open(LANDMARKS_PKL, 'rb') as f:
    dataset = pickle.load(f)

data   = np.array(dataset['data'],   dtype=np.float32)
labels = np.array(dataset['labels'])

counts = Counter(labels)
print(f"\n  Samples per class:")
for cls, cnt in sorted(counts.items()):
    warn = "  ← WARNING: need more data!" if cnt < 100 else ""
    print(f"    {cls.replace('_',' '):<28}: {cnt:5d}{warn}")
print(f"\n  Total  : {len(labels)}")
print(f"  Classes: {len(counts)}")
print(f"  Features per sample: {data.shape[1]}\n")

# ── StandardScaler — CRITICAL for feature ranges ─────────
# Our features have very different scales (coords 0-1, angles -1 to 1,
# distances vary by face size). StandardScaler normalises all to mean=0 std=1.
scaler     = StandardScaler()
data_scaled = scaler.fit_transform(data)

with open(SCALER_PKL, 'wb') as f:
    pickle.dump(scaler, f)
print(f"  [SAVED] Scaler → {SCALER_PKL}")

# ── Label encoding ────────────────────────────────────────
le             = LabelEncoder()
labels_encoded = le.fit_transform(labels)
labels_onehot  = to_categorical(labels_encoded)
num_classes    = len(le.classes_)

with open(ENCODER_PKL, 'wb') as f:
    pickle.dump(le, f)

# ── Class weights for imbalanced data ────────────────────
cw_arr  = compute_class_weight('balanced', classes=np.unique(labels_encoded), y=labels_encoded)
cw_dict = dict(enumerate(cw_arr))

# ── Train / test split ────────────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    data_scaled, labels_onehot,
    test_size=0.2, random_state=42, stratify=labels_encoded,
)
print(f"  Train: {len(X_train)} | Test: {len(X_test)}")
print(f"  Classes: {list(le.classes_)}\n")

# ── Model ─────────────────────────────────────────────────
REG = l2(0.0005)
model = Sequential([
    Dense(1024, activation='relu', kernel_regularizer=REG,
          input_shape=(data.shape[1],)),
    BatchNormalization(),
    Dropout(0.5),

    Dense(512, activation='relu', kernel_regularizer=REG),
    BatchNormalization(),
    Dropout(0.4),

    Dense(256, activation='relu', kernel_regularizer=REG),
    BatchNormalization(),
    Dropout(0.3),

    Dense(128, activation='relu', kernel_regularizer=REG),
    Dropout(0.2),

    Dense(num_classes, activation='softmax'),
])

model.compile(optimizer='adam',
              loss='categorical_crossentropy',
              metrics=['accuracy'])
model.summary()

# ── Train ─────────────────────────────────────────────────
callbacks = [
    EarlyStopping(patience=25, restore_best_weights=True, verbose=1),
    ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=10,
                      min_lr=1e-6, verbose=1),
]

history = model.fit(
    X_train, y_train,
    epochs=200,
    batch_size=32,
    validation_data=(X_test, y_test),
    class_weight=cw_dict,
    callbacks=callbacks,
    verbose=1,
)

# ── Evaluate ──────────────────────────────────────────────
loss, acc = model.evaluate(X_test, y_test, verbose=0)
print(f"\n  Test Accuracy : {acc * 100:.2f}%")
print(f"  Test Loss     : {loss:.4f}")

y_pred = np.argmax(model.predict(X_test, verbose=0), axis=1)
y_true = np.argmax(y_test, axis=1)
print(f"\n{classification_report(y_true, y_pred, target_names=[c.replace('_',' ') for c in le.classes_], digits=3)}")

# ── Save ──────────────────────────────────────────────────
model.save(MODEL_SAVE_PATH)
print(f"  [SAVED] Model   → {MODEL_SAVE_PATH}")
print(f"  [SAVED] Encoder → {ENCODER_PKL}")
print(f"  [SAVED] Scaler  → {SCALER_PKL}")

# ── Plot ──────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(13, 4))
fig.suptitle('Training Results', fontweight='bold')
axes[0].plot(history.history['accuracy'],     label='Train',      color='#00DC82')
axes[0].plot(history.history['val_accuracy'], label='Validation', color='#F59E0B', linestyle='--')
axes[0].set_title('Accuracy'); axes[0].legend()
axes[0].yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1))
axes[1].plot(history.history['loss'],         label='Train',      color='#00DC82')
axes[1].plot(history.history['val_loss'],     label='Validation', color='#F59E0B', linestyle='--')
axes[1].set_title('Loss'); axes[1].legend()
plt.tight_layout()
plot_path = os.path.join(BASE_DIR, 'training_results.png')
plt.savefig(plot_path, dpi=120, bbox_inches='tight')
plt.close()
print(f"  [SAVED] Plot    → {plot_path}")
print(f"\nNext: python src/webcam.py")