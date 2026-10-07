import cv2
import numpy as np
import tensorflow as tf


# =========================
# SETTINGS
# =========================

MODEL_PATH = "models/garbage_mobilenetv2.keras"

CLASS_NAMES = [
    "general_waste",
    "glass",
    "metal",
    "plastic"
]

IMG_SIZE = (224, 224)


# =========================
# LOAD MODEL
# =========================

print("Loading model...")

model = tf.keras.models.load_model(MODEL_PATH)

print("Model loaded!")
print("Starting webcam...")
print("Press Q to quit.")


# =========================
# START WEBCAM
# =========================

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("ERROR: Could not open webcam.")
    exit()


while True:

    ret, frame = cap.read()

    if not ret:
        print("ERROR: Could not read frame.")
        break

    # -------------------------
    # Prepare image
    # -------------------------

    image = cv2.resize(frame, IMG_SIZE)

    image = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2RGB
    )

    image = np.expand_dims(
        image,
        axis=0
    )

    # -------------------------
    # Prediction
    # -------------------------

    predictions = model.predict(
        image,
        verbose=0
    )

    predicted_index = np.argmax(predictions[0])

    predicted_class = CLASS_NAMES[predicted_index]

    confidence = predictions[0][predicted_index] * 100

    # -------------------------
    # Display result
    # -------------------------

    text = f"{predicted_class}: {confidence:.1f}%"

    cv2.putText(
        frame,
        text,
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2
    )

    cv2.imshow(
        "Garbage Classifier",
        frame
    )

    # Press Q to quit
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break


# =========================
# CLEAN UP
# =========================

cap.release()
cv2.destroyAllWindows()

print("Webcam stopped.")