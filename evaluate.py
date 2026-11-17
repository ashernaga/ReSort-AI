import csv
from pathlib import Path

import cv2
import tensorflow as tf
from sklearn.metrics import classification_report, confusion_matrix
import numpy as np


# =========================
# SETTINGS
# =========================

TEST_DIR = Path("dataset_split/test")
MODEL_PATH = Path("models/garbage_mobilenetv2.keras")

IMG_SIZE = (224, 224)
BATCH_SIZE = 32

CLASS_NAMES = [
    "general_waste",
    "glass",
    "metal",
    "plastic"
]


# =========================
# LOAD MODEL
# =========================

print("Loading model...")

model = tf.keras.models.load_model(MODEL_PATH)

print("Model loaded successfully.")


# =========================
# LOAD TEST DATA
# =========================

print("\nLoading test dataset...")

test_dataset = tf.keras.utils.image_dataset_from_directory(
    TEST_DIR,
    class_names=CLASS_NAMES,
    image_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    shuffle=False
)


# =========================
# BASIC TEST ACCURACY
# =========================

print("\nEvaluating model...")

test_loss, test_accuracy = model.evaluate(test_dataset)

print("\n--------------------------------")
print("Test Results")
print("--------------------------------")
print(f"Test Loss:     {test_loss:.4f}")
print(f"Test Accuracy: {test_accuracy:.4%}")


# =========================
# PREDICTIONS
# =========================

print("\nGenerating predictions...")

y_true = []
y_pred = []
y_conf = []

for images, labels in test_dataset:

    predictions = model.predict(
        images,
        verbose=0
    )

    predicted_classes = np.argmax(
        predictions,
        axis=1
    )

    y_true.extend(labels.numpy())
    y_pred.extend(predicted_classes)
    y_conf.extend(np.max(predictions, axis=1))


# =========================
# CLASSIFICATION REPORT
# =========================

print("\n--------------------------------")
print("Classification Report")
print("--------------------------------")

report = classification_report(
    y_true,
    y_pred,
    target_names=CLASS_NAMES,
    digits=4
)

print(report)

metal_index = CLASS_NAMES.index("metal")
file_paths = test_dataset.file_paths
wrong_as_metal = [
    file_paths[i]
    for i in range(len(y_true))
    if y_pred[i] == metal_index and y_true[i] != metal_index
]
missed_metal = [
    (file_paths[i], CLASS_NAMES[y_pred[i]])
    for i in range(len(y_true))
    if y_true[i] == metal_index and y_pred[i] != metal_index
]
print("\n--------------------------------")
print("Metal error analysis")
print("--------------------------------")
print(f"False positives (predicted metal, not metal): {len(wrong_as_metal)}")
for path in wrong_as_metal:
    print(f"  {path}")
print(f"False negatives (metal predicted as other): {len(missed_metal)}")
for path, predicted in missed_metal:
    print(f"  {path} -> {predicted}")

# =========================
# ERROR REPORT (ALL CLASSES)
# =========================

ERROR_REPORT_PATH = Path("models/error_report.csv")
ERROR_SHEET_PATH = Path("models/error_sheet.jpg")
SHEET_COLUMNS = 6
SHEET_MAX_IMAGES = 30

errors = sorted(
    (
        (file_paths[i], CLASS_NAMES[y_true[i]], CLASS_NAMES[y_pred[i]], float(y_conf[i]))
        for i in range(len(y_true))
        if y_true[i] != y_pred[i]
    ),
    key=lambda row: -row[3]
)

with open(ERROR_REPORT_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["path", "true_label", "predicted_label", "confidence"])
    for path, true_name, pred_name, conf in errors:
        writer.writerow([path, true_name, pred_name, f"{conf:.4f}"])

tiles = []
for path, true_name, pred_name, conf in errors[:SHEET_MAX_IMAGES]:
    img = cv2.imread(path)
    if img is None:
        continue
    img = cv2.resize(img, IMG_SIZE)
    label = f"true:{true_name} pred:{pred_name} {conf:.0%}"
    cv2.putText(img, label, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, label, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1, cv2.LINE_AA)
    tiles.append(img)

if tiles:
    while len(tiles) % SHEET_COLUMNS:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[r:r + SHEET_COLUMNS]) for r in range(0, len(tiles), SHEET_COLUMNS)]
    cv2.imwrite(str(ERROR_SHEET_PATH), np.vstack(rows))

print("\n--------------------------------")
print("Error report (all classes)")
print("--------------------------------")
print(f"Misclassified: {len(errors)} of {len(y_true)}")
print(f"Full list:     {ERROR_REPORT_PATH}")
print(f"Contact sheet: {ERROR_SHEET_PATH} (most confident errors first)")


# =========================
# CONFUSION MATRIX
# =========================

print("--------------------------------")
print("Confusion Matrix")
print("--------------------------------")

cm = confusion_matrix(
    y_true,
    y_pred
)

print(cm)