"""
Capture training photos from the webcam into dataset/extra_raw/<class>/.

Keys:
  1-4     choose the class (1 general_waste, 2 glass, 3 metal, 4 plastic)
  SPACE   save one photo
  B       burst mode on/off (saves a photo every BURST_SECONDS)
  T       box mode: follow the moving object, or fixed centre box
  Q       quit

Only the part of the frame inside the green box is saved, the same
region that webcam.py gives the model. Hold the item inside the box.
Tip: turn it, tilt it, change hands and distance between photos.
"""

import time
from pathlib import Path

import cv2
import numpy as np


# =========================
# SETTINGS
# =========================

CLASS_NAMES = ["general_waste", "glass", "metal", "plastic"]

OUTPUT_DIR = Path("dataset/extra_raw")

# Same box rules as webcam.py
BOX_FRACTION = 0.5
MIN_AREA_FRACTION = 0.01
MAX_AREA_FRACTION = 0.8
BOX_PADDING = 0.15

BURST_SECONDS = 0.6
TARGET_PER_CLASS = 200

# Colours (BGR)
GREEN = (0, 255, 0)
RED = (0, 0, 255)
WHITE = (255, 255, 255)


def count_images(class_name):
    folder = OUTPUT_DIR / class_name

    if not folder.exists():
        return 0

    return len(list(folder.glob("*.jpg")))


def find_box(frame, subtractor, kernel, follow):
    """Return (x1, y1, x2, y2). Same logic as webcam.py."""

    height, width = frame.shape[:2]

    if follow:
        mask = subtractor.apply(frame)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.dilate(mask, kernel, iterations=3)
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        frame_area = width * height
        contours = [
            c for c in contours
            if MIN_AREA_FRACTION * frame_area
            <= cv2.contourArea(c)
            <= MAX_AREA_FRACTION * frame_area
        ]

        if contours:
            bx, by, bw, bh = cv2.boundingRect(
                max(contours, key=cv2.contourArea)
            )
            pad_x = int(bw * BOX_PADDING)
            pad_y = int(bh * BOX_PADDING)

            return (
                max(bx - pad_x, 0),
                max(by - pad_y, 0),
                min(bx + bw + pad_x, width),
                min(by + bh + pad_y, height),
            )

    side = int(min(height, width) * BOX_FRACTION)
    x1 = (width - side) // 2
    y1 = (height - side) // 2

    return x1, y1, x1 + side, y1 + side


def save_crop(crop, class_name):
    folder = OUTPUT_DIR / class_name
    folder.mkdir(parents=True, exist_ok=True)

    name = f"cam_{class_name}_{int(time.time() * 1000)}.jpg"
    ok = cv2.imwrite(str(folder / name), crop)

    if not ok:
        print(f"ERROR: could not save {folder / name}")

    return ok


def main():
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("ERROR: Could not open webcam.")
        return

    subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
    kernel = np.ones((5, 5), np.uint8)

    current = 0
    burst = False
    follow = False
    last_burst = 0.0
    flash_until = 0.0

    print(__doc__)

    while True:
        ret, frame = cap.read()

        if not ret:
            print("ERROR: Could not read frame.")
            break

        x1, y1, x2, y2 = find_box(frame, subtractor, kernel, follow)

        # Copy the crop before drawing, so no overlay ends up in the photo.
        crop = frame[y1:y2, x1:x2].copy()
        class_name = CLASS_NAMES[current]
        now = time.time()

        if burst and now - last_burst >= BURST_SECONDS and crop.size:
            save_crop(crop, class_name)
            last_burst = now
            flash_until = now + 0.1

        display = frame.copy()
        box_colour = RED if now < flash_until else GREEN
        cv2.rectangle(display, (x1, y1), (x2, y2), box_colour, 2)

        count = count_images(class_name)
        cv2.putText(
            display,
            f"[{current + 1}] {class_name}: {count}/{TARGET_PER_CLASS}",
            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, GREEN, 2,
        )
        cv2.putText(
            display,
            f"burst: {'ON' if burst else 'off'}   "
            f"box: {'follow' if follow else 'centre'}",
            (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.7, WHITE, 2,
        )
        cv2.putText(
            display,
            "1-4 class  SPACE save  B burst  T box  Q quit",
            (20, display.shape[0] - 20),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 1,
        )

        cv2.imshow("Photo capture", display)

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break
        elif key in (ord("1"), ord("2"), ord("3"), ord("4")):
            current = key - ord("1")
            burst = False
        elif key == ord(" ") and crop.size:
            if save_crop(crop, class_name):
                flash_until = now + 0.1
        elif key == ord("b"):
            burst = not burst
        elif key == ord("t"):
            follow = not follow

    cap.release()
    cv2.destroyAllWindows()

    print("\nPhotos per class:")

    for name in CLASS_NAMES:
        print(f"  {name}: {count_images(name)}")


if __name__ == "__main__":
    main()
