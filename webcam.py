import argparse
import cv2
import numpy as np
import tensorflow as tf


# =========================
# SETTINGS
# =========================

parser = argparse.ArgumentParser(description="Live webcam garbage classifier.")
parser.add_argument("--model-path", default="models/garbage_mobilenetv2.keras", help="Path to the trained Keras model file.")
args = parser.parse_args()

CLASS_NAMES = [
    "general_waste",
    "glass",
    "metal",
    "plastic"
]

IMG_SIZE = (224, 224)

# Size of the bounding box as a fraction of the shorter frame side
BOX_FRACTION = 0.5

# Smallest moving region (fraction of the frame area) treated as an object
MIN_AREA_FRACTION = 0.01

# Largest region (fraction of the frame area); ignores whole-frame changes
MAX_AREA_FRACTION = 0.8

# Padding added around the tracked object, as a fraction of its size
BOX_PADDING = 0.15


# =========================
# LOAD MODEL
# =========================

print("Loading model...")

model = tf.keras.models.load_model(args.model_path)

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


# Background model used to find the moving garbage piece
subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
kernel = np.ones((5, 5), np.uint8)


while True:

    ret, frame = cap.read()

    if not ret:
        print("ERROR: Could not read frame.")
        break

    # -------------------------
    # Prepare image
    # -------------------------

    height, width = frame.shape[:2]

    # Track the moving object: foreground mask -> largest blob
    mask = subtractor.apply(frame)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.dilate(mask, kernel, iterations=3)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    frame_area = width * height
    contours = [
        c for c in contours
        if MIN_AREA_FRACTION * frame_area <= cv2.contourArea(c) <= MAX_AREA_FRACTION * frame_area
    ]

    if contours:
        bx, by, bw, bh = cv2.boundingRect(max(contours, key=cv2.contourArea))
        pad_x = int(bw * BOX_PADDING)
        pad_y = int(bh * BOX_PADDING)
        x1 = max(bx - pad_x, 0)
        y1 = max(by - pad_y, 0)
        x2 = min(bx + bw + pad_x, width)
        y2 = min(by + bh + pad_y, height)
    else:
        # Nothing moving: fall back to a centred box
        side = int(min(height, width) * BOX_FRACTION)
        x1 = (width - side) // 2
        y1 = (height - side) // 2
        x2 = x1 + side
        y2 = y1 + side

    # Classify only the region inside the box, not the whole frame
    roi = frame[y1:y2, x1:x2]
    image = cv2.resize(roi, IMG_SIZE)

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

    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

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