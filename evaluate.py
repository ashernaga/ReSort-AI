from pathlib import Path

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