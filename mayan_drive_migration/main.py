from __future__ import annotations

import argparse
import logging
import sys

from .config import load_settings
from .migrator import Migrator
from .validator import validate_manifest


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.env_file)
        configure_logging(settings.log_path)
        migrator = Migrator(settings)

        if args.command == "scan":
            manifest = migrator.scan()
            logging.info("Manifest contains %s files", len(manifest.items))
            return 0
        if args.command == "migrate":
            manifest = migrator.migrate(
                dry_run=args.dry_run,
                force=args.force,
                retry_failed=args.retry_failed,
            )
            logging.info("Migration manifest updated: %s files", len(manifest.items))
            return 0
        if args.command == "validate":
            report = validate_manifest(settings.manifest_path, settings.report_json_path, settings.report_csv_path)
            logging.info("Validation report: %s", report)
            return 0
    except Exception:
        logging.exception("Command failed")
        return 1
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="One-time Google Drive to Mayan EDMS migration utility")
    parser.add_argument("--env-file", default=None, help="Path to .env file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("scan", help="Scan Google Drive and build/update manifest")

    migrate = subparsers.add_parser("migrate", help="Upload pending manifest items to Mayan EDMS")
    migrate.add_argument("--dry-run", action="store_true", help="Do not create/upload anything in Mayan")
    migrate.add_argument("--resume", action="store_true", help="Resume pending items; default behavior")
    migrate.add_argument("--force", action="store_true", help="Reprocess all manifest items, including uploaded")
    migrate.add_argument("--retry-failed", action="store_true", help="Retry failed items as well as pending items")

    subparsers.add_parser("validate", help="Generate migration report from manifest")
    return parser


def configure_logging(log_path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


if __name__ == "__main__":
    raise SystemExit(main())
