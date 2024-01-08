from pathlib import Path
from PIL import Image
import os

def load_images_to_dict(directory):
    images_dict = {}
    for filename in os.listdir(directory):
        if filename.endswith('.jpg') or filename.endswith('.png'): # Add other image formats if needed
            path = os.path.join(directory, filename)
            image = Image.open(path)
            images_dict[filename] = image
    return images_dict

template_dir: Path = Path(__file__).resolve().parent / "template_images"
image_dict = load_images_to_dict(template_dir)