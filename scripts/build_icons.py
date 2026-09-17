"""Generate the small circular-ready icon set in static/images/icons/ from the
raw source art in artifacts/.

The source images are large (1024x1536) portrait renders with a gradient
"vignette" backdrop baked in and the actual subject sitting somewhere in the
upper half, not centered - a naive center-crop clips some of them (breakfast,
notably). This finds the subject automatically (edge-detect the grayscale
image, threshold it, take the bounding box of the "detailed" region) and crops
a square around it before downscaling.

Dev-time only - not a runtime dependency of the app, just how these committed
PNGs under static/images/icons/ were produced. Re-run after editing/replacing
anything in artifacts/:

    .venv/Scripts/python.exe scripts/build_icons.py
"""
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"
OUT_DIR = ROOT / "static" / "images" / "icons"

OUTPUT_SIZE = 256
EDGE_THRESHOLD = 30      # grayscale value above which an edge-map pixel counts as "subject"
BBOX_MARGIN = 0.25       # expand the detected subject bbox by this fraction on each side

# output_name -> source file in artifacts/
ICON_SOURCES = {
    "sun": "sun.png",
    "coffee": "coffee.png",
    "workout": "work-out.png",
    "code": "code.png",
    "chess": "Chess.png",
    "breakfast": "breakfast-1.png",
    "lunch": "lunch-1.png",
    "water": "lunch-2.png",
    "sleep": "bed-time.png",
    "default": "default-2.png",
    "admin": "admin.png",
    "user": "user.png",
}

# These already carry real transparency around a roughly-square subject -
# use the alpha channel's own bbox instead of edge-detecting the backdrop.
ALPHA_CROPPED_SOURCES = {"Chess.png", "breakfast-1.png"}


def square_bbox_from(bbox, canvas_size, margin=BBOX_MARGIN):
    """Expand bbox by margin, square it around its own center, clamp to canvas."""
    left, top, right, bottom = bbox
    cx, cy = (left + right) / 2, (top + bottom) / 2
    side = max(right - left, bottom - top) * (1 + margin)
    half = side / 2

    canvas_w, canvas_h = canvas_size
    half = min(half, canvas_w / 2, canvas_h / 2)  # never exceed the canvas

    cx = min(max(cx, half), canvas_w - half)
    cy = min(max(cy, half), canvas_h - half)

    return (round(cx - half), round(cy - half), round(cx + half), round(cy + half))


def find_subject_bbox(image):
    """Bounding box of the detailed subject vs. the smooth gradient backdrop."""
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
    mask = edges.point(lambda p: 255 if p > EDGE_THRESHOLD else 0)
    bbox = mask.getbbox()
    return bbox or (0, 0, *image.size)


def build_icon(name, source_filename):
    src_path = ARTIFACTS / source_filename
    image = Image.open(src_path).convert("RGBA")

    if source_filename in ALPHA_CROPPED_SOURCES:
        bbox = image.split()[-1].getbbox() or (0, 0, *image.size)
    else:
        bbox = find_subject_bbox(image)

    crop_box = square_bbox_from(bbox, image.size)
    cropped = image.crop(crop_box)
    resized = cropped.resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.LANCZOS)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{name}.png"
    resized.save(out_path, optimize=True)
    print(f"{source_filename:>20} -> {out_path.relative_to(ROOT)}  (cropped {crop_box}, {cropped.size})")


def main():
    for name, source_filename in ICON_SOURCES.items():
        build_icon(name, source_filename)


if __name__ == "__main__":
    main()
