import os
import subprocess
import tempfile
import uuid
import bleach
from PIL import Image, ImageOps


class InfographicMaker:
    def __init__(self, available_styles: list[str] | None = None) -> None:
        if available_styles:
            self.available_styles = available_styles
        else:
            self.available_styles = ['anubis', 'github', 'hacker', 'modest', 'retro','roryg-ghostwriter']
            
    @staticmethod
    def sanitize_markdown(markdown_content: str) -> str:
        # Define allowed tags and attributes
        allowed_tags = bleach.sanitizer.ALLOWED_TAGS + [
            'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'pre', 'code', 'blockquote', 'ul', 'ol', 'li', 'a', 'em', 'strong'
        ]
        allowed_attributes = {
            'a': ['href', 'title'],
            'img': ['src', 'alt', 'title'],
        }
        
        # Sanitize the markdown content
        return bleach.clean(
            markdown_content,
            tags=allowed_tags,
            attributes=allowed_attributes,
            strip=True
        )
    
    def make_infographic(self, markdown: str, style: str, border_color: str = 'black', border_width: int = 10) -> Image.Image:
        if style not in self.available_styles:
            raise ValueError(f"Style not available. Please pick from {self.available_styles}")
        
        markdown = self.sanitize_markdown(markdown)
        
        # Create a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            unique_id = str(uuid.uuid4())
            md_path = os.path.join(temp_dir, f'{unique_id}.md')
            html_path = os.path.join(temp_dir, f'{unique_id}.html')
            img_path = os.path.join(temp_dir, f'{unique_id}.png')

            # Write markdown content to a file
            with open(md_path, 'w') as md_file:
                md_file.write(markdown)

            # Generate HTML from Markdown using the specified style and specify the output directory
            subprocess.run(['generate-md', '--layout', style, '--input', md_path, '--output', temp_dir], check=True)

            # Convert the generated HTML to an image
            subprocess.run([
                'wkhtmltoimage',
                '--enable-local-file-access',
                html_path, img_path
            ], check=True)
            
            image = Image.open(img_path)
            image = ImageOps.expand(image, border=border_width, fill=border_color)

        return image

