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

    def make_cv(self, template_name: str, template_input: dict, file_path: str = "cv.png") -> str:
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
    resume_data = {
        "profile": {
            "name": "Shashank Srivastava",
            "email": "shashank12@mnnit.ac.in",
            "designation": "Assistant Professor",
            "institution": "Motilal Nehru National Institute of Technology, Allahabad, Prayagraj, India",
            "image_url": "http://mnnit.ac.in/ss/images/shashank.jpg",
            "graduation_year": "March, 2014",
            "education": "Doctorate, Indian Institute of Information Technology-Allahabad",
            "about": "DUGC of Computer Science & Engineering Department",
            "telephone": "0532-2271351",
            "work_experience": [
                {
                "title": "Senior Research Fellow",
                "company": "Indian Institute of Information Technology",
                "year": "2010-2014",
                "description": "Conducted advanced research in network security and published several papers in peer-reviewed journals."
                },
                {
                "title": "Lecturer",
                "company": "University of Technology",
                "year": "2006-2010",
                "description": "Taught undergraduate courses in computer science and supervised student projects."
                },
                {
                "title": "Software Developer Intern",
                "company": "Tech Innovations Inc.",
                "year": "2005",
                "description": "Developed a secure web application for internal use and contributed to various software development projects."
                }
            ],
            "workshops": [

            ],
            "education_history": [
                {
                "institution": "Indian Institute of Information Technology-Allahabad",
                "degree": "Doctorate",
                "field": "Information Security",
                "year": "2010-2014",
                "description": "Conducted research on secure mobile agent communication and received the 'Best Thesis Award'."
                },
                {
                "institution": "National Institute of Technology",
                "degree": "Master of Technology",
                "field": "Computer Science",
                "year": "2006-2008",
                "description": "Specialized in distributed systems and wrote a thesis on fault tolerance in distributed networks."
                },
                {
                "institution": "Regional Engineering College",
                "degree": "Bachelor of Technology",
                "field": "Computer Science and Engineering",
                "year": "2002-2006",
                "description": "Focused on software engineering principles and completed a capstone project on database management systems."
                }
            ]
        }
    }
    print(cv_maker.make_cv("SpectrumVitae", resume_data))
