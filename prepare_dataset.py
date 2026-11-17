from pathlib import Path
import hashlib
import shutil

# Original Kaggle dataset
SOURCE_DIR = Path("dataset/original_dataset/dataset-resized")

# New 4-class dataset
OUTPUT_DIR = Path("dataset_4class")

# Extra open-source images: put manually downloaded, already-relabelled
# images in dataset/extra_raw/<class>/ (git-ignored location).
EXTRA_SOURCE_DIR = Path("dataset/extra_raw")
EXTRA_OUTPUT_DIR = Path("dataset/extra")
TEST_DIR = Path("dataset_split/test")
MAX_TOTAL_BYTES = 2_000_000_000  # hard cap for all collected image files

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


def dir_bytes(folder):
    if not folder.exists():
        return 0
    return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_extra_sources():
    """Copy extra images into dataset/extra without exceeding the size cap.

    The cap covers dataset_4class + dataset/extra_raw + dataset/extra.
    Images identical to anything in dataset_4class or the fixed test set
    are skipped, so the old and new models share an untouched test set.
    """
    if not EXTRA_SOURCE_DIR.exists():
        print("\nNo dataset/extra_raw folder found; skipping extra sources.")
        return

    used = (
        dir_bytes(OUTPUT_DIR)
        + dir_bytes(EXTRA_SOURCE_DIR)
        + dir_bytes(EXTRA_OUTPUT_DIR)
    )
    print(f"\nStorage used before import: {used / 1e6:.1f} MB "
          f"of {MAX_TOTAL_BYTES / 1e6:.0f} MB")
    if used > MAX_TOTAL_BYTES:
        print("ERROR: size cap already exceeded; nothing imported.")
        return

    seen = set()
    for folder in (OUTPUT_DIR, TEST_DIR, EXTRA_OUTPUT_DIR):
        if folder.exists():
            for f in folder.rglob("*"):
                if f.is_file():
                    seen.add(file_hash(f))

    # Extra copies are added on top of the raw files already counted
    for class_name in sorted(set(CLASS_MAPPING.values())):
        source_folder = EXTRA_SOURCE_DIR / class_name
        if not source_folder.exists():
            continue
        destination_folder = EXTRA_OUTPUT_DIR / class_name
        destination_folder.mkdir(parents=True, exist_ok=True)

        added = skipped = 0
        for image_file in sorted(source_folder.iterdir()):
            if (
                image_file.is_symlink()
                or not image_file.is_file()
                or image_file.suffix.lower() not in IMAGE_EXTENSIONS
            ):
                continue
            size = image_file.stat().st_size
            if used + size > MAX_TOTAL_BYTES:
                print("Size cap reached; stopping import.")
                print(f"{class_name:15} {added:5} added, {skipped:5} duplicates")
                return
            digest = file_hash(image_file)
            if digest in seen:
                skipped += 1
                continue
            seen.add(digest)
            shutil.copy2(
                image_file,
                destination_folder / f"{digest[:16]}{image_file.suffix.lower()}"
            )
            used += size
            added += 1

        print(f"{class_name:15} {added:5} added, {skipped:5} duplicates")

    print(f"Storage used after import: {used / 1e6:.1f} MB")


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

    import_extra_sources()


if __name__ == "__main__":
    main()