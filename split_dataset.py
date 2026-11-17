from pathlib import Path
import shutil
import random

SOURCE_DIR = Path("dataset_4class")
OUTPUT_DIR = Path("dataset_split")

# Extra images (see prepare_dataset.py) go to train/validation only.
# The original dataset_split/test folder is the shared, untouched test set.
EXTRA_DIR = Path("dataset/extra")
V2_DIR = Path("dataset_split/v2")

TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
TEST_RATIO = 0.15

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp"
}

random.seed(42)


def build_v2_split():
    """Build dataset_split/v2 = old train/validation + new extra images.

    dataset_split/train, validation and test are never modified here.
    """
    if not EXTRA_DIR.exists():
        print("\nNo dataset/extra folder found; skipping v2 split.")
        return

    classes = ["general_waste", "glass", "metal", "plastic"]
    rng = random.Random(42)
    train_share = TRAIN_RATIO / (TRAIN_RATIO + VAL_RATIO)

    # Rebuild from scratch so stale files from earlier runs do not linger
    if V2_DIR.exists():
        shutil.rmtree(V2_DIR)

    for split in ["train", "validation"]:
        for class_name in classes:
            target = V2_DIR / split / class_name
            target.mkdir(parents=True, exist_ok=True)
            for image in (OUTPUT_DIR / split / class_name).iterdir():
                if image.is_file() and not (target / image.name).exists():
                    shutil.copy2(image, target / image.name)

    for class_name in classes:
        folder = EXTRA_DIR / class_name
        if not folder.exists():
            continue
        images = sorted(
            f for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
        )
        rng.shuffle(images)
        train_end = int(len(images) * train_share)
        for split, subset in (
            ("train", images[:train_end]),
            ("validation", images[train_end:]),
        ):
            for image in subset:
                shutil.copy2(image, V2_DIR / split / class_name / image.name)
        print(f"v2 {class_name}: +{len(images)} extra images")

    print(f"v2 dataset written to {V2_DIR} (test set: {OUTPUT_DIR / 'test'})")


def main():
    print("Creating train / validation / test datasets...\n")

    classes = [
        "general_waste",
        "glass",
        "metal",
        "plastic"
    ]

    # Create folders
    for split in ["train", "validation", "test"]:
        for class_name in classes:
            (OUTPUT_DIR / split / class_name).mkdir(
                parents=True,
                exist_ok=True
            )

    for class_name in classes:

        source_folder = SOURCE_DIR / class_name

        images = [
            file for file in source_folder.iterdir()
            if file.is_file()
            and file.suffix.lower() in IMAGE_EXTENSIONS
        ]

        random.shuffle(images)

        total = len(images)

        train_end = int(total * TRAIN_RATIO)
        val_end = train_end + int(total * VAL_RATIO)

        train_images = images[:train_end]
        val_images = images[train_end:val_end]
        test_images = images[val_end:]

        print(f"{class_name}:")
        print(f"  Train:      {len(train_images)}")
        print(f"  Validation: {len(val_images)}")
        print(f"  Test:       {len(test_images)}")

        for image in train_images:
            shutil.copy2(
                image,
                OUTPUT_DIR / "train" / class_name / image.name
            )

        for image in val_images:
            shutil.copy2(
                image,
                OUTPUT_DIR / "validation" / class_name / image.name
            )

        for image in test_images:
            shutil.copy2(
                image,
                OUTPUT_DIR / "test" / class_name / image.name
            )

    print("\n--------------------------------")
    print("Dataset split completed!")
    print("--------------------------------")

    build_v2_split()


if __name__ == "__main__":
    main()