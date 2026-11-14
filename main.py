import io
import json
import os
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

TARGET_URL = "https://docs.python.org/3/download.html"
SCOPES = ["https://www.googleapis.com/auth/drive"]

def get_drive_service():
    creds_json = os.environ.get("GDRIVE_CREDENTIALS")
    if not creds_json:
        raise ValueError("Missing GDRIVE_CREDENTIALS environment variable")
    creds_info = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def fetch_download_links(url):
    print(f"Fetching {url}...")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().endswith((".zip", ".pdf")):
            full_url = urljoin(url, href)
            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)
    print(f"Found {len(links)} unique .zip/.pdf links.")
    return links


def file_exists_in_folder(service, folder_id, filename):
    escaped_name = filename.replace("'", "\\'")
    query = (
        f"name = '{escaped_name}' and '{folder_id}' in parents and trashed = false"
    )
    result = (
        service.files()
        .list(
            q=query,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    return len(result.get("files", [])) > 0


def upload_file(service, folder_id, file_url):
    filename = os.path.basename(urlparse(file_url).path)
    if not filename:
        print(f"Skipping invalid URL: {file_url}")
        return
    if file_exists_in_folder(service, folder_id, filename):
        print(f"Skipping {filename}: already exists in target folder.")
        return
    print(f"Downloading {file_url}...")
    resp = requests.get(file_url, timeout=120)
    resp.raise_for_status()
    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(
        io.BytesIO(resp.content), mimetype="application/octet-stream", resumable=True
    )
    print(f"Uploading {filename} to Google Drive...")
    uploaded = (
        service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id, name",
            supportsAllDrives=True,
        )
        .execute()
    )
    print(f"Uploaded {uploaded.get('name')} (ID: {uploaded.get('id')})")


def main():
    folder_id = os.environ.get("GDRIVE_FOLDER_ID")
    if not folder_id:
        raise ValueError("Missing GDRIVE_FOLDER_ID environment variable")
    service = get_drive_service()
    links = fetch_download_links(TARGET_URL)
    for link in links:
        try:
            upload_file(service, folder_id, link)
        except Exception as exc:
            print(f"Error processing {link}: {exc}")


if __name__ == "__main__":
    main()
