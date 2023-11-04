from pydantic import BaseModel

class ResumeTemplate(BaseModel):
    name: str
    json_schema: str
    template_path: str
    css_path: str
    size: tuple[int, int]