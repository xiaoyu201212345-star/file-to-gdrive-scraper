import json
import os

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

DOWNLOAD_URL = "https://dl.twrp.me/nx563j/twrp-3.7.0_9-0-nx563j.img"
FILENAME = "twrp-3.7.0_9-0-nx563j.img"
HEADERS = {
    "Referer": "https://twrp.me/nubia/nubianx563j.html",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}
SCOPES = ["https://www.googleapis.com/auth/drive"]
MIN_FILE_SIZE = 1024 * 1024  # 1 MB


def get_drive_service():
    creds_json = os.environ.get("GDRIVE_CREDENTIALS")
    if not creds_json:
        raise ValueError("Missing GDRIVE_CREDENTIALS environment variable")
    creds_info = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def download_and_verify(url, headers, output_path):
    print(f"Downloading {url}...")
    resp = requests.get(url, headers=headers, stream=True, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Download failed with HTTP status code {resp.status_code}"
        )

    content_type = resp.headers.get("Content-Type", "").lower()
    if "text/html" in content_type:
        raise ValueError(
            f"Unexpected Content-Type '{content_type}': received HTML instead of binary image"
        )

    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    file_size = os.path.getsize(output_path)
    with open(output_path, "rb") as f:
        header_bytes = f.read(512).lstrip().lower()

    if b"<html" in header_bytes or b"<!doctype" in header_bytes:
        raise ValueError(
            "Downloaded file starts with HTML content (<html or <!doctype), aborting upload"
        )

    if file_size <= MIN_FILE_SIZE:
        raise ValueError(
            f"Downloaded file size ({file_size} bytes) is not greater than 1MB, aborting upload"
        )

    print(f"Verified binary image saved to {output_path} ({file_size} bytes).")


def file_exists_in_folder(service, filename, folder_id):
    safe_name = filename.replace("'", "\\'")
    query = f"name = '{safe_name}' and '{folder_id}' in parents and trashed = false"
    results = (
        service.files()
        .list(
            q=query,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = results.get("files", [])
    return files[0] if files else None


def upload_to_drive(service, file_path, filename, folder_id):
    media = MediaFileUpload(
        file_path, mimetype="application/octet-stream", resumable=True
    )
    metadata = {"name": filename, "parents": [folder_id]}
    print(f"Uploading {filename} to Google Drive folder {folder_id}...")
    uploaded = (
        service.files()
        .create(
            body=metadata,
            media_body=media,
            fields="id, name",
            supportsAllDrives=True,
        )
        .execute()
    )
    print(f"Successfully uploaded {uploaded.get('name')} (ID: {uploaded.get('id')}).")


def main():
    folder_id = os.environ.get("GDRIVE_FOLDER_ID")
    if not folder_id:
        raise ValueError("Missing GDRIVE_FOLDER_ID environment variable")

    download_and_verify(DOWNLOAD_URL, HEADERS, FILENAME)

    service = get_drive_service()
    existing = file_exists_in_folder(service, FILENAME, folder_id)
    if existing:
        print(
            f"File '{FILENAME}' already exists in folder {folder_id} "
            f"(ID: {existing.get('id')}). Skipping upload."
        )
        return

    upload_to_drive(service, FILENAME, FILENAME, folder_id)


if __name__ == "__main__":
    main()
