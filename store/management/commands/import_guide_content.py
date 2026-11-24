import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_slug
from django.db import transaction

from store.models import Guide


FIELDS = ("slug", "title", "summary", "body", "is_published", "sort_order")
DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "guide_content.json"


class Command(BaseCommand):
    help = "Import Guide-only content without overwriting existing records; preview by default."

    def add_arguments(self, parser):
        parser.add_argument("--file", type=Path, default=DEFAULT_FIXTURE)
        parser.add_argument("--apply", action="store_true", help="Create missing guides.")

    def handle(self, *args, **options):
        fixture_path = options["file"]
        try:
            records = json.loads(fixture_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CommandError(f"Could not read guide fixture {fixture_path}: {error}") from error

        records = self._validate_records(records)
        if options["apply"]:
            created, unchanged, conflicts = self._apply(records)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created: {created}; unchanged: {unchanged}; conflicts: {len(conflicts)}."
                )
            )
        else:
            created, unchanged, conflicts = self._preview(records)
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN ONLY: would create {created}; unchanged: {unchanged}; "
                    f"conflicts: {len(conflicts)}. No records were saved."
                )
            )

        for slug in conflicts:
            self.stdout.write(self.style.WARNING(f"Conflict left unchanged: {slug}"))

    @staticmethod
    def _validate_records(records):
        if not isinstance(records, list):
            raise CommandError("Guide fixture must contain a JSON list.")

        normalized = []
        seen_slugs = set()
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict) or set(record) != set(FIELDS):
                raise CommandError(
                    f"Guide record {index} must contain exactly: {', '.join(FIELDS)}."
                )

            slug = record["slug"]
            if not isinstance(slug, str):
                raise CommandError(f"Guide record {index} has an invalid slug.")
            try:
                validate_slug(slug)
            except ValidationError as error:
                raise CommandError(f"Guide record {index} has an invalid slug.") from error
            if len(slug) > 180 or slug in seen_slugs:
                raise CommandError(f"Guide record {index} has a duplicate or oversized slug.")
            seen_slugs.add(slug)

            for field, max_length in (("title", 160), ("summary", 300)):
                value = record[field]
                if not isinstance(value, str) or not value.strip() or len(value) > max_length:
                    raise CommandError(f"Guide record {index} has an invalid {field}.")
            if not isinstance(record["body"], str) or not record["body"].strip():
                raise CommandError(f"Guide record {index} has an empty body.")
            if not isinstance(record["is_published"], bool):
                raise CommandError(f"Guide record {index} has an invalid publication status.")
            sort_order = record["sort_order"]
            if isinstance(sort_order, bool) or not isinstance(sort_order, int) or sort_order < 0:
                raise CommandError(f"Guide record {index} has an invalid sort order.")

            normalized.append({field: record[field] for field in FIELDS})
        return normalized

    @staticmethod
    def _same_content(guide, record):
        return all(getattr(guide, field) == record[field] for field in FIELDS)

    def _preview(self, records):
        created = unchanged = 0
        conflicts = []
        for record in records:
            existing = Guide.objects.filter(slug=record["slug"]).first()
            if existing is None:
                created += 1
            elif self._same_content(existing, record):
                unchanged += 1
            else:
                conflicts.append(record["slug"])
        return created, unchanged, conflicts

    def _apply(self, records):
        created = unchanged = 0
        conflicts = []
        with transaction.atomic():
            for record in records:
                guide, was_created = Guide.objects.get_or_create(
                    slug=record["slug"],
                    defaults={field: record[field] for field in FIELDS if field != "slug"},
                )
                if was_created:
                    created += 1
                elif self._same_content(guide, record):
                    unchanged += 1
                else:
                    conflicts.append(record["slug"])
        return created, unchanged, conflicts
