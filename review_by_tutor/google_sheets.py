from __future__ import annotations

import json
from dataclasses import dataclass
from django.conf import settings
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

import config
from review_by_tutor.models import GoogleOAuthToken

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


@dataclass(frozen=True)
class CreatedSheet:
    spreadsheet_id: str
    web_view_link: str


def _drive_client():
    creds = Credentials.from_service_account_file(
        str(settings.GOOGLE_SA_JSON_PATH),
        scopes=DRIVE_SCOPES,
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def get_drive_service():
    row = GoogleOAuthToken.objects.filter(name="default").first()
    if not row:
        raise RuntimeError("Google OAuth не подключён: нет сохранённого токена. Открой /google/connect/")

    info = json.loads(row.token_json)
    creds = Credentials.from_authorized_user_info(info, scopes=DRIVE_SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            row.token_json = creds.to_json()
            row.save(update_fields=["token_json", "updated_at"])
        else:
            raise RuntimeError("Google credentials недействительны. Нужно переподключить /google/connect/")

    return build("drive", "v3", credentials=creds, cache_discovery=False)

def copy_template_sheet_for_user(*, user_id: int, user_name: str) -> tuple[str, str]:
    drive = get_drive_service()

    body = {
        "name": f"Интервью — {user_name} (ID {user_id})",
        "parents": [config.GOOGLE_DRIVE_INTERVIEW_FOLDER_ID],
    }

    res = drive.files().copy(
        fileId=config.GOOGLE_SHEETS_TEMPLATE_FILE_ID,
        body=body,
        fields="id,webViewLink",
    ).execute()

    return res["id"], res.get("webViewLink", "")

def create_user_sheet_from_template(
    *,
    user_display_name: str,
    user_id: int,
) -> CreatedSheet:
    drive = _drive_client()

    body = {
        "name": f"Интервью — {user_display_name or 'user'} (ID {user_id})",
        "parents": [config.GOOGLE_DRIVE_INTERVIEW_FOLDER_ID],
    }

    kwargs = {}

    try:
        copied = (
            drive.files()
            .copy(
                fileId=config.GOOGLE_SHEETS_TEMPLATE_FILE_ID,
                body=body,
                fields="id, webViewLink",
                **kwargs,
            )
            .execute()
        )
        spreadsheet_id = copied["id"]
        web_view_link = copied.get("webViewLink", "")

        return CreatedSheet(spreadsheet_id=spreadsheet_id, web_view_link=web_view_link)

    except HttpError as e:
        raise RuntimeError(f"Google Drive API error while copying template: {e}") from e
