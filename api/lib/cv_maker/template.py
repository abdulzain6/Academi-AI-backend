from pydantic import BaseModel
from typing import Optional

class ResumeTemplate(BaseModel):
    name: str
    json_schema: str
    template_path: str
    css_path: str
    size: tuple[int, int]
    element_id: Optional[str] = None
    