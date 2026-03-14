import os
import time
import shutil
from pathlib import Path
from datetime import datetime

from PIL import Image, ImageEnhance, ImageFilter, ExifTags
from escpos.printer import Usb

PRINTER_WIDTH = 576  # 80mm full width
INCOMING = Path("incoming")
PRINTS = Path("prints")
PROCESSED = Path("processed")
ARCHIVE_FILE = "archive_counter.txt"

VENDOR_ID = 0x1fc9
PRODUCT_ID = 0x2016


PRINTER = Usb(VENDOR_ID, PRODUCT_ID)

def get_archive_number():
    if not os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE, "w") as f:
            f.write("1")

    with open(ARCHIVE_FILE, "r") as f:
        content = f.read().strip()
        num = int(content) if content else 1

    with open(ARCHIVE_FILE, "w") as f:
        f.write(str(num + 1))

    return f"ARCHIVE {num:04d}"


def extract_exif(img):
    iso = shutter = aperture = "N/A"

    exif_data = img._getexif()
    if exif_data:
        exif = {
            ExifTags.TAGS.get(tag): value
            for tag, value in exif_data.items()
            if tag in ExifTags.TAGS
        }

        iso = exif.get("ISOSpeedRatings", "N/A")
        shutter = exif.get("ExposureTime", "N/A")
        aperture = exif.get("FNumber", "N/A")

        if isinstance(shutter, tuple):
            shutter = f"{shutter[0]}/{shutter[1]}"

        if isinstance(aperture, tuple):
            aperture = f"{round(aperture[0] / aperture[1], 1)}"

    return iso, shutter, aperture


def prepare_image(path):
    img = Image.open(path)
    img = img.convert("L")

    aspect_ratio = img.height / img.width
    new_height = int(PRINTER_WIDTH * aspect_ratio)
    img = img.resize((PRINTER_WIDTH, new_height), Image.LANCZOS)


    img = ImageEnhance.Contrast(img).enhance(3.5)
    img = ImageEnhance.Brightness(img).enhance(1)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=200))


    threshold = 110
    img = img.point(lambda x: 0 if x < threshold else 255, "1")

    return img


def process_image(path):
    iso, shutter, aperture = extract_exif(Image.open(path))

    archive_line = get_archive_number()
    settings_line = f"ISO {iso} | {shutter} | f/{aperture}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    processed_img = prepare_image(path)

    temp_output = PRINTS / path.name
    processed_img.save(temp_output)

    p = PRINTER

    p.set(align="center")
    p.image(str(temp_output))


    p.set(align="left")
    p.text("\n")
    p.text(settings_line + "\n")
    p.text(archive_line + "\n")
    p.text(timestamp + "\n")


    logo_path = Path("logo.png")
    if logo_path.exists():
        p.set(align="center")
        p.text("\n")
        p.image(str(logo_path))

    p.feed(12)
    p.cut()

    shutil.move(path, PROCESSED / path.name)

    print("===================================")
    print("[EVENT] IMAGE_PRINTED")
    print(f"[ARCHIVE] {archive_line}")
    print("[STATUS] Physical print complete.")
    print("===================================\n")


def main():
    print("ARCHIVE PRINTER ACTIVE")
    print("Drop .JPG files into incoming/\n")

    known_files = set()

    while True:
        current_files = set(INCOMING.glob("*.JPG"))
        new_files = current_files - known_files

        for file in sorted(new_files):
            try:
                process_image(file)
            except Exception as e:
                print("Print failed:", e)

        known_files = set(INCOMING.glob("*.JPG"))
        time.sleep(1)


if __name__ == "__main__":
    main()
