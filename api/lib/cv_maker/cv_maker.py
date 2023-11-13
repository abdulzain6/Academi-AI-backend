import json, jsonschema
import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .template import ResumeTemplate
from html2image import Html2Image
from langchain.chat_models.base import BaseChatModel
from langchain.chains import create_extraction_chain, LLMChain
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate


class CVMaker:
    def __init__(
        self,
        templates: list[ResumeTemplate],
        chrome_path: str,
        chat_model: BaseChatModel,
    ) -> None:
        self.templates = templates
        self.chrome_path = chrome_path
        self.chat_model = chat_model

    def get_template_names(self) -> list[str]:
        return [template.name for template in self.templates]

    def get_all_templates(self) -> list[dict]:
        return [
            {"name": template.name, "schema": json.loads(template.json_schema)}
            for template in self.templates
        ]

    def get_template_by_name(self, name: str) -> ResumeTemplate | None:
        for template in self.templates:
            if template.name == name:
                return template

    def make_cv_from_string(
        self,
        template_name: str,
        string: str,
        output_file_path: str = "/tmp",
        output_file_name: str = "cv.png",
    ):
        template = self.get_template_by_name(template_name)
        chain = LLMChain(
            llm=self.chat_model,
            prompt=ChatPromptTemplate(messages=[
                    SystemMessagePromptTemplate.from_template(
                        """
Extract relevant information for CV generation from the passage provided below. Follow these guidelines:
You must add placeholders if the fields are not provided (important)
The data will be used to make a cv.
Dont miss required fields (Very important) or it will cause error
You must follow the schema.
Ensure the extracted information is accurate and contextually relevant to the content of the passage.
                        """
                    ),
                    HumanMessagePromptTemplate.from_template(
                        """
You must follow the schema, Failure to do so will cause error.
Schema:
{schema}
                        
Passage (Add placeholders if missing specially socials and follow the damn schema):
{input}

The json with no missing fields and schema followed:"""
                    )
                ],
                input_variables=["input", "schema"]
            )                           
        )
        input_dict = json.loads(chain.run(input=string, schema=template.json_schema))
        logging.info(f"Extracted data {input_dict}")
        return self.make_cv(
            template_name,
            input_dict,
            output_file_path=output_file_path,
            output_file_name=output_file_name,
        )

    def make_cv(
        self,
        template_name: str,
        template_input: dict,
        output_file_path: str = "/tmp",
        output_file_name: str = "cv.png",
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
        return self.html_to_image(
            resume_html,
            Path(template.css_path).read_text(),
            output_file_path=output_file_path,
            size=template.size,
            file_name=output_file_name,
        )

    def html_to_image(
        self,
        html: str,
        css: str,
        output_file_path: str,
        file_name: str,
        size: tuple[int, int],
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
        hti.output_path = output_file_path
        return hti.screenshot(html_str=html, css_str=css, save_as=file_name)


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
            "hobbies": "Painting, Hiking, Reading",
        },
        "employment_history": [
            {
                "position": "Graphic Designer",
                "years": "2005 - 2007",
                "details": "Involved in various design projects, focusing on branding and visual identities.",
            },
            {
                "position": "Creative Director",
                "years": "2008 - Present",
                "details": "Leading the creative team and overseeing all design and campaign projects.",
            },
        ],
        "education": [
            {
                "institution": "High School of Arts",
                "qualification": "High School Diploma",
                "date_completed": "May 2004",
                "gpa": "3.5",
            },
            {
                "institution": "University of Design",
                "qualification": "Bachelor of Fine Arts",
                "date_completed": "July 2007",
                "gpa": "3.8",
            },
        ],
        "personal_skills": [
            "Social Commitment",
            "Organization",
            "Creativity",
            "Communication",
            "Teamwork",
        ],
        "technical_skills": [
            "Photoshop",
            "Illustrator",
            "InDesign",
            "Flash",
            "Dreamweaver",
            "XHTML/CSS",
            "JavaScript",
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
            },
        },
    }

    print(cv_maker.make_cv("Elegant Spectrum", fake_data))
