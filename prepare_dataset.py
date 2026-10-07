from pathlib import Path
import shutil

# Original Kaggle dataset
SOURCE_DIR = Path("dataset/original_dataset/dataset-resized")

# New 4-class dataset
OUTPUT_DIR = Path("dataset_4class")

# Original class -> new class
CLASS_MAPPING = {
    "glass": "glass",
    "plastic": "plastic",
    "metal": "metal",
    "cardboard": "general_waste",
    "paper": "general_waste",
    "trash": "general_waste",
}

# Image types we accept
IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp"
}


def main():

    print("Preparing 4-class garbage dataset...\n")

    # Create output folders
    for new_class in set(CLASS_MAPPING.values()):
        (OUTPUT_DIR / new_class).mkdir(
            parents=True,
            exist_ok=True
        )

    total_images = 0

    # Process each original class
    for old_class, new_class in CLASS_MAPPING.items():

        source_folder = SOURCE_DIR / old_class
        destination_folder = OUTPUT_DIR / new_class

        if not source_folder.exists():
            print(f"ERROR: {source_folder} does not exist")
            continue

        count = 0

        for image_file in source_folder.iterdir():

            if (
                image_file.is_file()
                and image_file.suffix.lower() in IMAGE_EXTENSIONS
            ):

                # Prevent filename conflicts
                new_filename = f"{old_class}_{image_file.name}"

                destination = destination_folder / new_filename

                shutil.copy2(
                    image_file,
                    destination
                )

                count += 1
                total_images += 1

        print(
            f"{old_class:12} -> "
            f"{new_class:15} "
            f"{count:4} images"
        )

    print("\n--------------------------------")
    print("Dataset preparation completed!")
    print("--------------------------------")
    print(f"Total images: {total_images}")
    print(f"Location: {OUTPUT_DIR.absolute()}")


if __name__ == "__main__":
    main()