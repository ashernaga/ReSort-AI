from pathlib import Path

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input


# =========================
# SETTINGS
# =========================

DATASET_DIR = Path("dataset_split")

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
# SAVE MODEL
# =========================

MODEL_DIR = Path("models")
MODEL_DIR.mkdir(exist_ok=True)

model_path = MODEL_DIR / "garbage_mobilenetv2.keras"

model.save(model_path)

print("\n--------------------------------")
print("Training completed!")
print("--------------------------------")
print(f"Model saved to: {model_path}")