from django.core.management.base import BaseCommand

from nde.listing_access import start_trial_if_eligible
from nde.models import RemoteUser


class Command(BaseCommand):
    """
    Accorde l'essai gratuit de 14 jours aux agences déjà vérifiées avant l'introduction de
    l'abonnement annonces (le déclenchement automatique ne s'applique qu'aux vérifications
    faites après ce changement — sans ce rattrapage, ces comptes seraient bloqués d'emblée).
    """

    help = "Démarre l'essai gratuit de 14 jours pour les agences déjà vérifiées qui ne l'ont pas encore reçu."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche les comptes concernés sans rien modifier.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        candidates = RemoteUser.objects.filter(
            role=RemoteUser.Roles.AGENCE,
            verification_status=RemoteUser.VerificationStatus.VERIFIE,
            listing_trial_used=False,
        )

        count = 0
        for user in candidates:
            if dry_run:
                self.stdout.write(f"[dry-run] essai à démarrer : {user.email}")
                count += 1
                continue
            before = user.listing_trial_used
            start_trial_if_eligible(user)
            user.refresh_from_db(fields=["listing_trial_used"])
            if user.listing_trial_used and not before:
                self.stdout.write(f"Essai démarré : {user.email}")
                count += 1

        suffix = " (dry-run, aucune modification)" if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{count} agence(s) concernée(s){suffix}."))
