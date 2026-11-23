from django.core.management.base import BaseCommand
from django.db import transaction

from seed_gachghar_catalogue import setup_catalogue


class Command(BaseCommand):
    help = "Safely create or activate the owner-supplied 26-product GachGhar catalogue."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Commit the catalogue changes. Without this flag the command previews and rolls back.",
        )

    def handle(self, *args, **options):
        if options["apply"]:
            setup_catalogue()
            return

        with transaction.atomic():
            setup_catalogue()
            transaction.set_rollback(True)
        self.stdout.write(self.style.WARNING("DRY RUN ONLY: no database changes were saved. Use --apply to commit."))
