import os
import json, jsonschema
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape
from template import ResumeTemplate
from html2image import Html2Image


class CVMaker:
    def __init__(self, templates: list[ResumeTemplate], chrome_path: str) -> None:
        self.templates = templates
        self.chrome_path = chrome_path

    def get_template_names(self) -> list[str]:
        return [template.name for template in self.templates]

    def get_template_by_name(self, name: str) -> ResumeTemplate | None:
        for template in self.templates:
            if template.name == name:
                return template

    def copy_files_to_temp_dir(
        self, source_dir: str, temp_dir_prefix: Optional[str] = None
    ) -> str:
        """
        Copies all files and directories from the source directory to a new temporary directory.

        :param source_dir: The path of the directory whose contents are to be copied.
        :param temp_dir_prefix: An optional prefix for the name of the temporary directory.
        :return: The path to the newly created temporary directory.
        """
        # Create a temporary directory
        temp_dir = tempfile.mkdtemp(prefix=temp_dir_prefix)
        for item in os.listdir(source_dir):
            source_item = os.path.join(source_dir, item)
            destination_item = os.path.join(temp_dir, item)
            if os.path.isdir(source_item):
                shutil.copytree(source_item, destination_item)
            else:
                shutil.copy2(source_item, destination_item)
        return temp_dir

    def make_cv(
        self, template_name: str, template_input: dict, file_path: str = "cv.png"
    ) -> str:
        if template_name not in self.get_template_names():
            raise ValueError("Template does not exist")

        template = self.get_template_by_name(template_name)
        try:
            jsonschema.validate(
                instance=template_input, schema=json.loads(template.json_schema)
            )
        except jsonschema.ValidationError as e:
            raise ValueError("Error in input format") from e

        template_dir = Path(template.template_path).parent
        file_name = Path(template.template_path).name
        env = Environment(
            loader=FileSystemLoader(searchpath=template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )
        template_jinga = env.get_template(file_name)
        resume_html = template_jinga.render(template_input)
        return self.html_to_pdf(
            resume_html, Path(template.css_path).read_text(), file_path, template.size
        )

    def html_to_pdf(
        self, html: str, css: str, output_file_path: str, size: tuple[int, int]
    ) -> None:
        hti = Html2Image(
            browser_executable=self.chrome_path,
            size=size,
            custom_flags=[
                "--disable-gpu",
                "--force-device-scale-factor=2",
                "--hide-scrollbars",
                "--disable-animations",
                "--start-maximized",
            ],
        )
        return hti.screenshot(html_str=html, css_str=css, save_as=output_file_path)


if __name__ == "__main__":
    from template_loader import template_loader

    cv_maker = CVMaker(template_loader(), "/usr/bin/google-chrome")
    fake_data = data = {
    "personal_details": {
        "first_name": "Antony",
        "last_name": "Smith",
        "image_url": "https://dribbble.s3.amazonaws.com/users/10958/screenshots/271458/librarian.jpg",
        "nationality": "American",
        "location": "New York, NY",
        "birthday": "1985-06-15",
        "hobbies": "Painting, Hiking, Reading"
    },
    "employment_history": [
        {
            "position": "Graphic Designer",
            "years": "2005 - 2007",
            "details": "Involved in various design projects, focusing on branding and visual identities."
        },
        {
            "position": "Creative Director",
            "years": "2008 - Present",
            "details": "Leading the creative team and overseeing all design and campaign projects."
        }
    ],
    "education": [
        {
            "institution": "High School of Arts",
            "qualification": "High School Diploma",
            "date_completed": "May 2004",
            "gpa": "3.5"
        },
        {
            "institution": "University of Design",
            "qualification": "Bachelor of Fine Arts",
            "date_completed": "July 2007",
            "gpa": "3.8"
        }
    ],
    "personal_skills": [
        "Social Commitment",
        "Organization",
        "Creativity",
        "Communication",
        "Teamwork"
    ],
    "technical_skills": [
        "Photoshop",
        "Illustrator",
        "InDesign",
        "Flash",
        "Dreamweaver",
        "XHTML/CSS",
        "JavaScript"
    ],
    "contact": {
        "phone": "+1234567890",
        "email": "antony.smith@example.com",
        "website": "www.antonymsmithdesigns.com",
        "socials": {
            "linkedin": "linkedin.com/in/antonymsmith",
            "twitter": "@antonymdesigns",
            "dribbble": "dribbble.com/antonymsmith",
            # Add or remove social media accounts as needed
        }
    }
}

    print(cv_maker.make_cv("Elegant Spectrum", fake_data))
