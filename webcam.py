import cv2
import numpy as np
import tensorflow as tf

MODEL_PATH = "models/garbage_mobilenetv2.keras"

CLASS_NAMES = [
    "general_waste",
    "glass",
    "metal",
    "plastic"
]

IMG_SIZE = (224, 224)

print("Loading model...")
model = tf.keras.models.load_model(MODEL_PATH)
print("Model loaded!")
print("Starting webcam...")
print("Press Q to quit.")

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not cap.isOpened():
    print("ERROR: Could not open webcam.")
    exit()

frame_count = 0
text = ""

while True:
    ret, frame = cap.read()

    if not ret:
        print("ERROR: Could not read frame.")
        break

    if frame_count % 3 == 0:
        image = cv2.resize(frame, IMG_SIZE)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = np.expand_dims(image, axis=0)

        predictions = model(image, training=False).numpy()

        predicted_index = np.argmax(predictions[0])
        predicted_class = CLASS_NAMES[predicted_index]
        confidence = predictions[0][predicted_index] * 100

        text = f"{predicted_class}: {confidence:.1f}%"

    frame_count += 1

    cv2.putText(frame, text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.imshow("Garbage Classifier", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
print("Webcam stopped.")