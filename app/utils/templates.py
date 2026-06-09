from __future__ import annotations

from fastapi.templating import Jinja2Templates

from app.utils.url import safe_href


def create_templates(directory: str = "templates") -> Jinja2Templates:
    templates = Jinja2Templates(directory=directory)
    templates.env.filters["safe_href"] = safe_href
    return templates
