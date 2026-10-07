from pathlib import Path
import shutil
import random

SOURCE_DIR = Path("dataset_4class")
OUTPUT_DIR = Path("dataset_split")

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


if __name__ == "__main__":
    main()