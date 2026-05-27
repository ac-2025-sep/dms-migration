# Mayan Drive Migration

One-time migration utility for moving files from Google Drive into Mayan EDMS while preserving Drive paths as Mayan cabinets and extracting business metadata from filenames.

This is not a sync system. It scans, builds a manifest, migrates pending files, and writes validation reports for retry and audit.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file:

```env
GOOGLE_SERVICE_ACCOUNT_FILE=D:\path\to\service-account.json
GOOGLE_DRIVE_ROOT_FOLDER_ID=your-root-folder-id
MAYAN_BASE_URL=https://mayan.example.com
MAYAN_API_TOKEN=your-token
MAYAN_DEFAULT_DOCUMENT_TYPE_ID=1
MANIFEST_PATH=state\migration_manifest.json
DOWNLOAD_TEMP_DIR=state\downloads
DRY_RUN=true

# Optional
WORKSPACE_EXPORT_MODE=office
REPORT_JSON_PATH=state\migration_report.json
REPORT_CSV_PATH=state\migration_report.csv
LOG_PATH=migration.log
```

## Google Drive Setup

1. Create a Google Cloud service account.
2. Enable the Google Drive API.
3. Download the service account JSON key.
4. Share the Drive root folder with the service account email address.

Google Workspace files are exported by default to Office formats:

- Google Docs: `.docx`
- Google Sheets: `.xlsx`
- Google Slides: `.pptx`

Set `WORKSPACE_EXPORT_MODE=pdf` to export all Workspace files as PDFs.

## Mayan Setup

Create a Mayan API token and set `MAYAN_API_TOKEN`. Requests use:

```http
Authorization: Token <token>
```

`MAYAN_DEFAULT_DOCUMENT_TYPE_ID` must be a valid Mayan document type ID. Metadata is mapped by metadata type label/name, and the tool tries to create missing metadata types where the Mayan API permits it.

## Commands

```powershell
python -m mayan_drive_migration.main scan
python -m mayan_drive_migration.main migrate --dry-run
python -m mayan_drive_migration.main migrate --resume
python -m mayan_drive_migration.main migrate --retry-failed
python -m mayan_drive_migration.main migrate --force
python -m mayan_drive_migration.main validate
```

`--resume` is the default behavior: uploaded files are skipped. `--force` reprocesses all manifest entries.

## Metadata Extraction

Example:

```text
isdr_wa_en_1f_v1- Base Doc - Identify Spurious Medicines.docx
```

Extracted metadata:

- `content_code`: `isdr`
- `channel_or_format`: `wa`
- `language`: `en`
- `section_code`: `1f`
- `version`: `v1`
- `document_stage`: `Base Doc`
- `title`: `Identify Spurious Medicines`
- `original_filename`: full filename

The tool also stores Google source metadata:

- `google_file_id`
- `google_drive_full_path`
- `google_modified_time`
- `google_mime_type`
- `migration_timestamp`
- `source`: `Google Drive`

If a filename does not match the expected pattern, migration continues and uses the filename stem as the title.

## Cabinets and Tags

The Google Drive parent path is used as the target cabinet path. If true nested cabinets are unavailable in the Mayan API, the tool creates a flattened cabinet label using ` >`, such as:

```text
PE MATERIAL > PE Topic wise Content > Medication Safety
```

Tags are derived from folder names, language, version, document stage, and safe title keywords.

## Reports and Retry

The manifest tracks every file with:

- `pending`
- `uploaded`
- `failed`
- `skipped`

Failures are isolated per file. Use `migrate --retry-failed` to retry only failed and pending items. Use `validate` to generate JSON and CSV reports.

## Limitations

- This is a one-time migration utility, not continuous sync.
- Mayan API endpoint details can vary by Mayan version; check `migration.log` for exact API errors.
- Metadata type creation depends on Mayan permissions and configuration.
- Background document processing in Mayan may continue after an upload returns `202 Accepted`.


##
add the files to be uploaded to google service account
