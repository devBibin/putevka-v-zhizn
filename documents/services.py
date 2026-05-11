import io
from django.core.files.base import ContentFile
from docxtpl import DocxTemplate
from .jinja_env import build_jinja_env

def render_docx_bytes(template_file, context: dict) -> bytes:
    doc = DocxTemplate(template_file.path)
    env = build_jinja_env()
    doc.render(context, jinja_env=env)
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()
