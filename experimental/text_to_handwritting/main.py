from PIL import Image, ImageFont, ImageDraw
import numpy as np

def add_noise(image, noise_level=10):
    """
    Adds random noise to an image using numpy for faster processing.
    Ensures the alpha channel remains unaffected.
    :param image: PIL Image object.
    :param noise_level: Integer that determines the noise intensity.
    """
    # Convert PIL image to numpy array
    np_image = np.array(image)
    
    # Generate noise array for RGB channels only
    noise = np.random.randint(-noise_level, noise_level, np_image.shape[:2] + (3,), dtype='int16')
    
    # Add noise and ensure values remain in valid range for RGB channels only
    np_image[..., :3] = np.clip(np_image[..., :3].astype('int16') + noise, 0, 255).astype('uint8')
    
    # Convert back to PIL image
    return Image.fromarray(np_image)

def render_text_to_handwriting(
    text: str,
    font_path: str,
    output_path: str,
    font_size: int = 20,
    ink_color: str = "black",
    dpi: int = 300,
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
    if transparent and add_noise_effect:
        raise ValueError("Cannot add noise to transparent images")
    
    width_in_pixels = int(8.27 * dpi)
    height_in_pixels = int(11.69 * dpi)

    if transparent:
        image = Image.new('RGBA', (width_in_pixels, height_in_pixels), (0, 0, 0, 0))
    elif background_image_path:
        image = Image.open(background_image_path).resize((width_in_pixels, height_in_pixels))
    else:
        image = Image.new('RGB', (width_in_pixels, height_in_pixels), 'white')

    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, int(font_size * dpi / 72))

    current_x = margin
    current_y = vertical_position
    line_height = calculate_line_height(draw, font, line_spacing_extra)
    text_heights = [(current_y, current_y + line_height)]

    words = text.replace('\n', ' \n ').split(' ')
    for word in words:
        if word == '\n':
            current_y += line_height
            current_x = margin
            text_heights.append((current_y, current_y + line_height))
            continue

        word_width = sum(draw.textbbox((0, 0), letter, font=font)[2] for letter in word) + letter_spacing * len(word)
        
        # Add space after the word, plus additional word spacing.
        space_after_word = word_spacing

        # Check if the word plus the space after it exceeds the width, move to next line.
        if current_x + word_width + space_after_word > width_in_pixels - margin:
            current_y += line_height
            current_x = margin
            text_heights.append((current_y, current_y + line_height))
        
        for letter in word:
            draw.text((current_x, current_y), letter, font=font, fill=ink_color)
            current_x += draw.textbbox((0, 0), letter, font=font)[2] + letter_spacing
        
        current_x += space_after_word

    if paper_lines:
        add_paper_lines(draw, width_in_pixels, height_in_pixels, margin, text_heights)

    if add_noise_effect:
        image = add_noise(image, noise_level=noise_level)

    image.save(output_path, "PNG")

def calculate_line_height(draw, font, extra_spacing):
    bbox = draw.textbbox((0, 0), "Hygp", font=font)
    return bbox[3] - bbox[1] + extra_spacing

def add_paper_lines(draw, width, height, margin, text_heights, buffer=4):
    """
    Add paper lines without intersecting text, placing them just below the text.
    """
    for lower, upper in text_heights:
        line_y = upper + buffer  # Small buffer to place line just below the text
        if line_y < height - margin:  # Ensure line doesn't go beyond the bottom margin
            draw.line([(margin, line_y), (width - margin, line_y)], fill="#000")
            
    max_line_height = max(upper - lower for lower, upper in text_heights) + buffer

    while line_y < height - margin:
        draw.line([(margin, line_y), (width - margin, line_y)], fill="#000")
        line_y += max_line_height  # Use the maximum line height as the interval



# Example usage
render_text_to_handwriting(
"""Explicitly Handle Spaces: Instead of using the width of a single space character to add space after words, define a fixed amount of space to add after each word to ensure uniformity.

Review Letter Spacing Calculation: Ensure that letter spacing is consistently applied between all letters and adjust the calculation if necessary.

Adjust Word Wrapping Logic: Make sure the word wrapping logic precisely accounts for both the word's width and the additional spacing that will follow the word.
""" *10,
    "Pencil Studio.otf",
    "output_handwritten.png",
    font_size=20,
    ink_color="darkblue",
    vertical_position=100,
    margin=50,
    paper_lines=True,
    transparent=False
)
