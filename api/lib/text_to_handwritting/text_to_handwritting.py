import io
import re
import tempfile
import numpy as np
from PIL import Image, ImageFont, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import os

def load_fonts(font_dir: str) -> dict:
    fonts = {}
    for filename in os.listdir(font_dir):
        if filename.endswith(('.otf', '.ttf')):
            font_name = os.path.splitext(filename)[0]
            fonts[font_name] = os.path.abspath(os.path.join(font_dir, filename))
    return fonts

# Assuming the fonts directory is in the same directory as this script
script_dir = os.path.dirname(os.path.abspath(__file__))
font_dir = os.path.join(script_dir, 'fonts')

# Global dictionary of fonts
FONTS = load_fonts(font_dir)

class HandwritingRenderer:
    def __init__(
        self,
        font_path: str,
        font_size: int = 20,
        ink_color: str = "black",
        dpi: int = 100,
        vertical_position: int = 50,
        transparent: bool = False,
        margin: int = 50,
        paper_lines: bool = False,
        line_spacing_extra: int = 5,
        add_noise_effect: bool = True,
        noise_level: int = 20,
        background_image_path: str = None,
        word_spacing: int = 60,
        letter_spacing: int = 4
    ):
        self.font_path = font_path
        self.font_size = font_size
        self.ink_color = ink_color
        self.dpi = dpi
        self.vertical_position = vertical_position
        self.transparent = transparent
        self.margin = margin
        self.paper_lines = paper_lines
        self.line_spacing_extra = line_spacing_extra
        self.add_noise_effect = add_noise_effect
        self.noise_level = noise_level
        self.background_image_path = background_image_path
        self.word_spacing = word_spacing
        self.letter_spacing = letter_spacing

        self.width_in_pixels = int(8.27 * dpi)
        self.height_in_pixels = int(11.69 * dpi)
        self.font = ImageFont.truetype(font_path, int(font_size * dpi / 72))
    
    def add_noise(self, image: Image.Image, noise_level: int = 10) -> Image.Image:
        np_image = np.array(image)
        noise = np.random.randint(-noise_level, noise_level, np_image.shape[:2] + (3,), dtype='int16')
        np_image[..., :3] = np.clip(np_image[..., :3].astype('int16') + noise, 0, 255).astype('uint8')
        return Image.fromarray(np_image)
    
    def calculate_line_height(self, draw: ImageDraw.Draw, font: ImageFont.FreeTypeFont, extra_spacing: int) -> int:
        bbox = draw.textbbox((0, 0), "Hygp", font=font)
        return bbox[3] - bbox[1] + extra_spacing

    def add_paper_lines(self, draw: ImageDraw.Draw, width: int, height: int, margin: int, text_heights: list[tuple[int, int]], buffer: int = 4):
        for lower, upper in text_heights:
            line_y = upper + buffer
            if line_y < height - margin:
                draw.line([(margin, line_y), (width - margin, line_y)], fill="#000")
        
        max_line_height = max(upper - lower for lower, upper in text_heights) + buffer

        while line_y < height - margin:
            draw.line([(margin, line_y), (width - margin, line_y)], fill="#000")
            line_y += max_line_height

    def render_text_to_handwriting_single_page(self, text: str) -> Image.Image:
        if self.transparent and self.add_noise_effect:
            raise ValueError("Cannot add noise to transparent images")
        
        if self.transparent:
            image = Image.new('RGBA', (self.width_in_pixels, self.height_in_pixels), (0, 0, 0, 0))
        elif self.background_image_path:
            image = Image.open(self.background_image_path).resize((self.width_in_pixels, self.height_in_pixels))
        else:
            image = Image.new('RGB', (self.width_in_pixels, self.height_in_pixels), 'white')

        draw = ImageDraw.Draw(image)
        current_x = self.margin
        current_y = self.vertical_position
        line_height = self.calculate_line_height(draw, self.font, self.line_spacing_extra)
        text_heights = [(current_y, current_y + line_height)]

        text = re.sub(r'(?<=\n) +', lambda match: '\x01' * len(match.group()), text)
        text = text.replace('\n', ' \n ')
        words = text.split(' ')

        for word in words:
            if word == '\n':
                current_y += line_height
                current_x = self.margin
                text_heights.append((current_y, current_y + line_height))
                continue
            
            if '\x01' in word:
                leading_spaces = word.count('\x01')
                current_x += leading_spaces * (draw.textbbox((0, 0), "H", font=self.font)[2] + self.letter_spacing)
                word = word.replace('\x01', '')

            word_width = sum(draw.textbbox((0, 0), letter, font=self.font)[2] for letter in word) + self.letter_spacing * len(word)
            space_after_word = self.word_spacing

            if current_x + word_width > self.width_in_pixels - self.margin:
                current_y += line_height
                current_x = self.margin
                text_heights.append((current_y, current_y + line_height))
                if current_y + line_height > self.height_in_pixels - self.margin:
                    break

            for letter in word:
                draw.text((current_x, current_y), letter, font=self.font, fill=self.ink_color)
                current_x += draw.textbbox((0, 0), letter, font=self.font)[2] + self.letter_spacing

            current_x += space_after_word

        if self.paper_lines:
            self.add_paper_lines(draw, self.width_in_pixels, self.height_in_pixels, self.margin, text_heights)

        if self.add_noise_effect:
            image = self.add_noise(image, noise_level=self.noise_level)

        return image

    def render_text_to_handwriting(self, text: str):
        max_lines_per_page = (self.height_in_pixels - self.vertical_position - self.margin) // self.calculate_line_height(
            ImageDraw.Draw(Image.new('RGB', (self.width_in_pixels, self.height_in_pixels), 'white')),
            self.font,
            self.line_spacing_extra
        )

        wrapped_text = self.wrap_text(text, max_lines_per_page)
        print(wrapped_text)
        images = []        
        for i, page_text in enumerate(wrapped_text):
            image = self.render_text_to_handwriting_single_page(page_text)
            images.append(image)
        return images
    
    def wrap_text(self, text: str, max_lines_per_page: int) -> list[str]:
        lines = text.split('\n')
        wrapped_lines = []
        current_page = []
        current_line_count = 0

        for line in lines:
            current_page.append(line)
            current_line_count += 1

            if current_line_count >= max_lines_per_page:
                wrapped_lines.append('\n'.join(current_page))
                current_page = []
                current_line_count = 0

        if current_page:
            wrapped_lines.append('\n'.join(current_page))

        return wrapped_lines
    
    def save_images_to_pdf(self, images: list[Image.Image]) -> bytes:
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        for image in images:
            with tempfile.NamedTemporaryFile(suffix=".png") as temp_file:
                image.save(temp_file, format="PNG")
                temp_file.seek(0)
                c.drawImage(temp_file.name, 0, 0, width=A4[0], height=A4[1])
                c.showPage()
        c.save()

        buffer.seek(0)
        return buffer.getvalue()

