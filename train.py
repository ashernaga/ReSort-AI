import argparse
import json
from pathlib import Path

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input


# =========================
# SETTINGS
# =========================

parser = argparse.ArgumentParser(description="Train the waste classifier.")
parser.add_argument(
    "--data-dir", default="dataset_split",
    help="folder with train/ and validation/ (e.g. dataset_split/v2)"
)
parser.add_argument(
    "--model-path", default="models/garbage_mobilenetv2.keras",
    help="where to save the trained model"
)
parser.add_argument(
    "--overwrite", action="store_true",
    help="allow replacing an existing model file"
)
parser.add_argument(
    "--fine-tune-layers", type=int, default=0,
    help="after training, unfreeze the last N MobileNetV2 layers and fine-tune (0 = off)"
)
args = parser.parse_args()

DATASET_DIR = Path(args.data_dir)
MODEL_OUT_PATH = Path(args.model_path)

if MODEL_OUT_PATH.exists() and not args.overwrite:
    raise SystemExit(
        f"{MODEL_OUT_PATH} already exists. Choose another --model-path "
        "or pass --overwrite."
    )

IMG_SIZE = (224, 224)
BATCH_SIZE = 32
NUM_CLASSES = 4
EPOCHS = 15

CLASS_NAMES = [
    "general_waste",
    "glass",
    "metal",
    "plastic"
]


# =========================
# LOAD DATASET
# =========================

print("Loading datasets...")

train_dataset = tf.keras.utils.image_dataset_from_directory(
    DATASET_DIR / "train",
    class_names=CLASS_NAMES,
    image_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    shuffle=True,
    seed=42
)

validation_dataset = tf.keras.utils.image_dataset_from_directory(
    DATASET_DIR / "validation",
    class_names=CLASS_NAMES,
    image_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    shuffle=False
)


print("\nClasses:")
print(CLASS_NAMES)


# =========================
# PERFORMANCE
# =========================

AUTOTUNE = tf.data.AUTOTUNE

train_dataset = train_dataset.prefetch(AUTOTUNE)
validation_dataset = validation_dataset.prefetch(AUTOTUNE)


# =========================
# DATA AUGMENTATION
# =========================

data_augmentation = keras.Sequential([
    layers.RandomFlip("horizontal"),
    layers.RandomRotation(0.1),
    layers.RandomZoom(0.1),
    layers.RandomBrightness(0.2),
    layers.RandomContrast(0.2),
])


# =========================
# MOBILENETV2
# =========================

print("\nLoading MobileNetV2...")

base_model = MobileNetV2(
    input_shape=(224, 224, 3),
    include_top=False,
    weights="imagenet"
)

# Freeze the pretrained layers
base_model.trainable = False


# =========================
# BUILD MODEL
# =========================

inputs = keras.Input(shape=(224, 224, 3))

x = data_augmentation(inputs)

x = preprocess_input(x)

x = base_model(
    x,
    training=False
)

x = layers.GlobalAveragePooling2D()(x)

x = layers.Dropout(0.2)(x)

outputs = layers.Dense(
    NUM_CLASSES,
    activation="softmax"
)(x)

model = keras.Model(
    inputs,
    outputs
)


# =========================
# COMPILE
# =========================

model.compile(
    optimizer=keras.optimizers.Adam(
        learning_rate=0.001
    ),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"]
)


# =========================
# SHOW MODEL
# =========================

model.summary()


# =========================
# CALLBACKS
# =========================

callbacks = [

    keras.callbacks.EarlyStopping(
        monitor="val_loss",
        patience=4,
        restore_best_weights=True
    ),

    keras.callbacks.ReduceLROnPlateau(
        monitor="val_loss",
        factor=0.2,
        patience=2,
        min_lr=1e-6
    )

]


# =========================
# TRAIN
# =========================

print("\nStarting training...\n")

history = model.fit(
    train_dataset,
    validation_data=validation_dataset,
    epochs=EPOCHS,
    callbacks=callbacks
)


# =========================
# FINE-TUNING (optional)
# =========================

if args.fine_tune_layers > 0:
    print(f"\nFine-tuning last {args.fine_tune_layers} layers...\n")
    phase1_best_val_loss = min(history.history["val_loss"])
    phase1_weights = model.get_weights()

    base_model.trainable = True
    for layer in base_model.layers[:-args.fine_tune_layers]:
        layer.trainable = False
    for layer in base_model.layers[-args.fine_tune_layers:]:
        # Keep BatchNormalization layers frozen
        layer.trainable = not isinstance(layer, layers.BatchNormalization)

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=1e-5),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"]
    )

    fine_tune_history = model.fit(
        train_dataset,
        validation_data=validation_dataset,
        epochs=15,
        callbacks=callbacks
    )

    if min(fine_tune_history.history["val_loss"]) < phase1_best_val_loss:
        for key, values in fine_tune_history.history.items():
            history.history[key] = history.history[key] + values
    else:
        print("\nFine-tuning did not improve val_loss; keeping the original weights.")
        model.set_weights(phase1_weights)


# =========================
# SAVE MODEL
# =========================

model_path = MODEL_OUT_PATH
model_path.parent.mkdir(parents=True, exist_ok=True)

model.save(model_path)

# Record how this model was trained, so models can be compared later
run_info = {
    "data_dir": str(DATASET_DIR),
    "epochs_run": len(history.history["loss"]),
    "best_val_accuracy": max(history.history["val_accuracy"]),
    "img_size": list(IMG_SIZE),
    "classes": CLASS_NAMES,
}
model_path.with_suffix(".json").write_text(json.dumps(run_info, indent=2))

print("\n--------------------------------")
print("Training completed!")
print("--------------------------------")
print(f"Model saved to: {model_path}")