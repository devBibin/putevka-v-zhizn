from jinja2 import Environment
from datetime import datetime
try:
    from num2words import num2words
except Exception:
    num2words = None

def date_ru(value, fmt="%d.%m.%Y"):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except Exception:
            return value
    return value.strftime(fmt)

def money_text_ru(value):
    if value is None or value == "":
        return ""
    if num2words is None:
        return str(value)
    return num2words(value, lang="ru")

def build_jinja_env():
    env = Environment(autoescape=True)
    env.filters["date_ru"] = date_ru
    env.filters["money_ru"] = money_text_ru
    return env
