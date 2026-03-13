from PIL import Image
import sys

def crop_transparent(image_path, output_path):
    img = Image.open(image_path)
    img = img.convert("RGBA")
    bbox = img.getbbox()
    if bbox:
        img_cropped = img.crop(bbox)
        img_cropped.save(output_path)
        print(f"Cropped precisely to {bbox}")
    else:
        print("Image is entirely transparent or empty")

try:
    crop_transparent('./ui/src/assets/synchrony-logo-square.png', './ui/src/assets/synchrony-logo-square.png')
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
