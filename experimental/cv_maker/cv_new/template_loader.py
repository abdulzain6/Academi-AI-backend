import json
from pathlib import Path
from template import ResumeTemplate


def template_loader(template_dir: str = None) -> list[ResumeTemplate]:
    if template_dir is None:
        template_dir: Path = Path(__file__).resolve().parent / "templates"
    else:
        template_dir: Path = Path(template_dir)

    templates = [entry for entry in template_dir.iterdir() if entry.is_dir()]
    if not templates:
        return []

    resume_templates = []
    for template_path in templates:
        info_path = template_path / "info.json"
        schema_path = template_path / "schema.json"
        info = json.loads(info_path.read_text()) if info_path.exists() else None
        schema = schema_path.read_text() if schema_path.exists() else None
        resume_templates.append(
            ResumeTemplate(
                name=info.get("name"),
                json_schema=schema,
                template_path=str(template_path / info.get("path")),
                css_path=str(template_path / info.get("css_path")),
                size=tuple(info.get("size"))
            )
        )
    return resume_templates


if __name__ == "__main__":
    print(template_loader()[0].json_schema)
