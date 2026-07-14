from django.core.management.base import BaseCommand
from django.db.models import Q

from nde.geocoding import geocode_address
from nde.models import Maison


class Command(BaseCommand):
    """
    Géocode les maisons dont la latitude/longitude est manquante (nécessaire pour apparaître
    sous forme de pin sur la carte). À relancer après toute correction du géocodage
    (ex: mauvais countrycodes) pour rattraper les annonces déjà créées.
    """

    help = "Géocode les maisons sans latitude/longitude à partir de leur adresse."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche les annonces concernées sans rien modifier.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        candidates = Maison.objects.filter(
            Q(latitude__isnull=True) | Q(longitude__isnull=True)
        )

        ok, failed = 0, 0
        for maison in candidates:
            if dry_run:
                self.stdout.write(f"[dry-run] à géocoder : {maison.id} — {maison.adresse}, {maison.ville}")
                continue

            coords = geocode_address(maison.adresse, maison.ville, maison.code_postal)
            if coords:
                maison.latitude, maison.longitude = coords
                maison.save(update_fields=["latitude", "longitude"])
                self.stdout.write(f"OK : {maison.id} — {maison.adresse}, {maison.ville} -> {coords}")
                ok += 1
            else:
                self.stdout.write(self.style.WARNING(f"ÉCHEC : {maison.id} — {maison.adresse}, {maison.ville}"))
                failed += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"{candidates.count()} annonce(s) à géocoder (dry-run)."))
        else:
            self.stdout.write(self.style.SUCCESS(f"{ok} géocodée(s), {failed} échec(s)."))
