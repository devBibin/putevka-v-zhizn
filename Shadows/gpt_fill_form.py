import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import django
from dotenv import load_dotenv
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from openai import OpenAI

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

load_dotenv()

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "Putevka.settings"),
)
django.setup()

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

FORM_RANGE = os.getenv("INTERVIEW_FORM_RANGE", "A1:K300")
MIN_NONEMPTY_ANSWERS = int(os.getenv("MIN_NONEMPTY_ANSWERS", "1"))

from review_by_tutor.models import Interview, InterviewSheetTemplate

try:
    from review_by_tutor.models import InterviewTemplate  # noqa: E402
except Exception:
    InterviewTemplate = None


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("GPT_TOKEN")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
POLLING_INTERVAL = int(os.getenv("INTERVIEW_FILL_POLLING_INTERVAL", "60"))
BATCH_LIMIT = int(os.getenv("INTERVIEW_FILL_BATCH_LIMIT", "2"))

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "Ты — ассистент интервьюера. "
    "Тебе дан список полей формы и транскрипт разговора. "
    "Нужно заполнить поля максимально точно по смыслу, без выдумок. "
    "Если данных нет — верни пустую строку."
)

USER_PROMPT = (
    "Верни ТОЛЬКО JSON (без текста вокруг):\n"
    "- ключи: ровно как id из списка (пример: \"Лист1!D6\")\n"
    "- значения: что вписать в соответствующую ячейку\n"
    "Правила:\n"
    "1) Не придумывай факты.\n"
    "2) Пиши кратко и по делу, но полезно интервьюеру.\n"
    "3) Если поле предполагает 'да/нет' — верни 'да' или 'нет' (если ясно), иначе пусто.\n"
    "4) Если данных нет — верни пустую строку.\n"
)


def _load_oauth_row():
    from review_by_tutor.models import GoogleOAuthToken  # type: ignore

    row = GoogleOAuthToken.objects.filter(name="default").first()
    if not row:
        raise RuntimeError(
            "Google OAuth не подключён: нет записи GoogleOAuthToken(name='default'). "
            "Сначала пройди /google/connect/ в админке."
        )
    return row


def _load_user_creds() -> Credentials:
    row = _load_oauth_row()
    info = json.loads(row.token_json)

    scopes = DRIVE_SCOPES
    if not scopes:
        raise RuntimeError("нет DRIVE_SCOPES.")

    creds = Credentials.from_authorized_user_info(info, scopes=scopes)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            row.token_json = creds.to_json()
            row.save(update_fields=["token_json", "updated_at"])
        else:
            raise RuntimeError("Google credentials недействительны. Нужна переподключка /google/connect/.")

    return creds


def get_drive_service():
    creds = _load_user_creds()
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def get_sheets_service():
    creds = _load_user_creds()
    return build("sheets", "v4", credentials=creds, cache_discovery=False)

def _is_empty_like(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        s = v.strip()
        return s == "" or set(s) <= {"_", "—", "-", " "}
    return False


def _col_to_letters(col: int) -> str:
    s = ""
    while col > 0:
        col, r = divmod(col - 1, 26)
        s = chr(65 + r) + s
    return s


def _a1(row: int, col: int) -> str:
    return f"{_col_to_letters(col)}{row}"


def _normalize_rect(values: List[List[Any]]) -> Tuple[List[List[Any]], int, int]:
    max_cols = max((len(r) for r in values), default=0)
    if max_cols == 0:
        return values, 0, 0
    for r in values:
        if len(r) < max_cols:
            r.extend([None] * (max_cols - len(r)))
    return values, len(values), max_cols


def validate_fields_json(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {"version": 1, "scan_range": FORM_RANGE, "fields": []}
    if not isinstance(obj, dict):
        raise RuntimeError("fields_json должен быть объектом JSON (dict).")

    version = obj.get("version", 1)
    scan_range = obj.get("scan_range", FORM_RANGE)
    fields = obj.get("fields", [])
    if not isinstance(fields, list):
        raise RuntimeError("fields_json.fields должен быть списком.")

    cleaned = []
    seen = set()
    for it in fields:
        if not isinstance(it, dict):
            continue
        cell_id = str(it.get("id", "")).strip()
        if "!" not in cell_id:
            continue
        if cell_id in seen:
            continue
        seen.add(cell_id)

        cleaned.append({
            "id": cell_id,
            "label": str(it.get("label", "")).strip(),
            "enabled": bool(it.get("enabled", True)),
            "kind": str(it.get("kind", "")).strip(),
        })

    return {"version": version, "scan_range": scan_range, "fields": cleaned}


def get_active_template() -> InterviewSheetTemplate:
    tpl = InterviewSheetTemplate.objects.filter(is_active=True).first()
    if not tpl:
        raise RuntimeError("Нет активного InterviewSheetTemplate")
    return tpl

def ensure_template_fields(tpl: InterviewSheetTemplate) -> List[Dict[str, str]]:
    cfg = validate_fields_json(tpl.fields_json)
    fields = [f for f in cfg["fields"] if f["enabled"]]

    if fields:
        return fields

    sheets = get_sheets_service()
    found = extract_fields_from_spreadsheet(sheets, tpl.template_spreadsheet_id, cfg["scan_range"])

    new_fields = []
    for f in found:
        new_fields.append({"id": f["id"], "label": f["label"], "enabled": True, "kind": ""})

    tpl.fields_json = {"version": 1, "scan_range": cfg["scan_range"], "fields": new_fields}
    tpl.fields_scanned_at = timezone.now()
    tpl.save(update_fields=["fields_json", "fields_scanned_at", "updated_at"])

    return [f for f in new_fields if f["enabled"]]


def extract_fields_from_spreadsheet(
    sheets_service,
    spreadsheet_id: str,
    scan_range: str = "C1:E300",
) -> List[Dict[str, str]]:
    """
    ЖЁСТКИЙ КОНТРАКТ:
    - label всегда в колонке C
    - ответ всегда в колонке E
    """
    meta = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(title))",
    ).execute()

    fields: List[Dict[str, str]] = []

    for sh in meta.get("sheets", []):
        title = sh["properties"]["title"]
        rng = f"{title}!{scan_range}"

        resp = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=rng,
            valueRenderOption="UNFORMATTED_VALUE",
        ).execute()

        rows = resp.get("values", [])
        if not rows:
            continue

        for i, row in enumerate(rows, start=1):
            if len(row) < 1:
                continue

            label = row[2]
            if not isinstance(label, str):
                continue

            label = label.strip()
            if len(label) == 0:
                continue

            sheet_row = i

            target = f"E{sheet_row}"
            fields.append({
                "id": f"{title}!{target}",
                "label": label,
                "enabled": True,
                "kind": "",
            })

    return fields



def fill_spreadsheet(
    sheets_service,
    spreadsheet_id: str,
    fields: List[Dict[str, str]],
    answers_by_id: Dict[str, str],
) -> None:
    data = []
    for f in fields:
        key = f["id"]
        value = (answers_by_id.get(key, "") or "").strip()
        data.append({"range": key, "values": [[value]]})

    sheets_service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()


def ensure_interview_sheet(interview: Interview, tpl: InterviewSheetTemplate) -> str:
    sheet_id = getattr(interview, "google_sheet_id", "") or ""
    if sheet_id:
        return sheet_id

    template_id = getattr(settings, "GOOGLE_SHEETS_TEMPLATE_FILE_ID", None)
    folder_id = getattr(settings, "GOOGLE_DRIVE_INTERVIEW_FOLDER_ID", None)
    if not template_id or not folder_id:
        raise RuntimeError(
            "В settings должны быть GOOGLE_SHEETS_TEMPLATE_FILE_ID и GOOGLE_DRIVE_INTERVIEW_FOLDER_ID."
        )

    drive = get_drive_service()

    name = f"Interview {interview.id} — user {interview.user_id}"
    res = drive.files().copy(
        fileId=tpl.template_spreadsheet_id,
        body={"name": name, "parents": [tpl.target_folder_id]},
        fields="id,webViewLink",
    ).execute()

    new_id = res["id"]
    new_url = res.get("webViewLink", "")

    if hasattr(interview, "google_sheet_id"):
        interview.google_sheet_id = new_id
    if hasattr(interview, "google_sheet_url"):
        interview.google_sheet_url = new_url

    save_fields = []
    if hasattr(interview, "google_sheet_id"):
        save_fields.append("google_sheet_id")
    if hasattr(interview, "google_sheet_url"):
        save_fields.append("google_sheet_url")
    if save_fields:
        interview.save(update_fields=save_fields)

    return new_id

def ask_openai_fill(fields: List[Dict[str, str]], transcript: str) -> Dict[str, str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY/GPT_TOKEN не установлен.")

    payload = [{"id": f["id"], "label": f.get("label", ""), "kind": f.get("kind", "")} for f in fields]

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
            {"role": "user", "content": f"Поля формы (id + label):\n{json.dumps(payload, ensure_ascii=False)}"},
            {"role": "user", "content": f"Транскрипт:\n{transcript}"},
        ],
        response_format={"type": "json_object"},
    )

    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)

    out: Dict[str, str] = {}
    for f in fields:
        k = f["id"]
        v = data.get(k, "")
        if v is None:
            out[k] = ""
        elif isinstance(v, (dict, list)):
            out[k] = json.dumps(v, ensure_ascii=False)
        else:
            out[k] = str(v).strip()

    nonempty = sum(1 for v in out.values() if v and v.strip())
    logger.info(f"[DBG] answers non-empty: {nonempty}/{len(out)}")
    if nonempty < MIN_NONEMPTY_ANSWERS:
        raise RuntimeError(f"LLM returned too few non-empty answers: {nonempty}/{len(out)}")

    return out


def pick_interviews_to_fill(limit: int):
    qs = (
        Interview.objects
        .filter(transcript_status="DONE")
        .exclude(transcript__isnull=True)
        .exclude(transcript__exact="")
        .filter(sheet_fill_status__in=["PENDING", "ERROR"])
        .order_by("updated_at")[:limit]
    )
    return qs



def process_one(interview_id: int) -> None:
    with transaction.atomic():
        obj = Interview.objects.select_for_update().get(pk=interview_id)

        if obj.sheet_fill_status == "DONE":
            return
        if obj.sheet_fill_status == "PROCESSING":
            return

        transcript = (obj.transcript or "").strip()
        if not transcript:
            return

        obj.sheet_fill_status = "PROCESSING"
        obj.sheet_fill_error = ""
        obj.save(update_fields=["sheet_fill_status", "sheet_fill_error", "updated_at"])

    try:
        tpl = get_active_template()
        sheets = get_sheets_service()
        spreadsheet_id = ensure_interview_sheet(obj, tpl)

        fields = ensure_template_fields(tpl)
        if not fields:
            raise RuntimeError("В шаблоне нет полей для заполнения (fields_json пуст и скан не нашёл).")

        answers = ask_openai_fill(fields, transcript)
        fill_spreadsheet(sheets, spreadsheet_id, fields, answers)

        with transaction.atomic():
            obj = Interview.objects.select_for_update().get(pk=interview_id)
            obj.sheet_fill_status = "DONE"
            obj.sheet_filled_at = timezone.now()
            obj.sheet_fill_error = ""
            obj.save(update_fields=["sheet_fill_status", "sheet_filled_at", "sheet_fill_error", "updated_at"])

    except Exception as e:
        with transaction.atomic():
            obj = Interview.objects.select_for_update().get(pk=interview_id)
            obj.sheet_fill_status = "ERROR"
            obj.sheet_fill_error = str(e)
            obj.save(update_fields=["sheet_fill_status", "sheet_fill_error", "updated_at"])
        raise



def fill_pending_interviews():
    interviews = pick_interviews_to_fill(BATCH_LIMIT)
    if not interviews.exists():
        logger.info("Нет интервью для заполнения формы (Google Sheets).")
        return

    logger.info(f"Найдено {interviews.count()} интервью для заполнения формы (Google Sheets).")

    for it in interviews:
        logger.info(f"Заполнение Google Sheet для Interview ID {it.id} ...")
        try:
            process_one(it.id)
            logger.info(f"  -> OK Interview ID {it.id}")
        except HttpError as e:
            logger.error(f"  -> FAIL Interview ID {it.id}: Google API error: {e}")
        except Exception as e:
            logger.error(f"  -> FAIL Interview ID {it.id}: {e}")


def main():
    logger.info("Запуск фонового скрипта Interview Form Filler (Google Sheets)...")
    while True:
        try:
            fill_pending_interviews()
        except Exception as e:
            logger.error(f"Критическая ошибка в главном цикле: {e}")
            time.sleep(30)

        logger.info(f"Следующая проверка через {POLLING_INTERVAL} секунд...")
        time.sleep(POLLING_INTERVAL)


if __name__ == "__main__":
    main()
