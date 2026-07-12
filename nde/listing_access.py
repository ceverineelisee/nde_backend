"""Quota de publication d'annonces (propriétaires/agences) et abonnement KPay (Mobile Money)."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from nde.models import ListingSubscriptionPayment, Maison, RemoteUser


def subscription_active(user) -> bool:
    exp = getattr(user, "listing_subscription_until", None)
    return bool(exp and exp > timezone.now())


def is_trial_period(user) -> bool:
    """True si l'abonnement en cours provient de l'essai gratuit (pas d'un paiement)."""
    if not getattr(user, "listing_trial_used", False):
        return False
    return not ListingSubscriptionPayment.objects.filter(
        user=user, status=ListingSubscriptionPayment.Status.PAID
    ).exists()


def price_for(user) -> int:
    if getattr(user, "role", "") == RemoteUser.Roles.AGENCE:
        return settings.LISTING_AGENCE_SUBSCRIPTION_PRICE_XAF
    return settings.LISTING_PROPRIETAIRE_SUBSCRIPTION_PRICE_XAF


def daily_published_count(user) -> int:
    return Maison.objects.filter(
        proprietaire=user,
        statut="publiee",
        date_publication__date=timezone.localdate(),
    ).count()


def can_publish_more(user) -> bool:
    if subscription_active(user):
        return True
    if getattr(user, "role", "") == RemoteUser.Roles.AGENCE:
        return False
    return daily_published_count(user) < settings.LISTING_PROPRIETAIRE_FREE_DAILY_QUOTA


def start_trial_if_eligible(user) -> None:
    """Démarre l'essai gratuit de 14 jours pour une agence nouvellement vérifiée (usage unique)."""
    if user.role != RemoteUser.Roles.AGENCE:
        return
    if user.listing_trial_used:
        return
    if user.listing_subscription_until and user.listing_subscription_until > timezone.now():
        return
    user.listing_subscription_until = timezone.now() + timedelta(days=settings.LISTING_TRIAL_DAYS)
    user.listing_trial_used = True
    user.save(update_fields=["listing_subscription_until", "listing_trial_used", "updated_at"])


def listing_access_payload(user) -> dict:
    """Résumé pour le frontend (dashboard propriétaire/agence, page abonnement)."""
    exp = getattr(user, "listing_subscription_until", None)
    payload = {
        "role": user.role,
        "subscription_active": subscription_active(user),
        "subscription_until": exp.isoformat() if exp else None,
        "is_trial": is_trial_period(user),
        "price_xaf": price_for(user),
    }

    if user.role == RemoteUser.Roles.AGENCE:
        payload["blocked"] = not subscription_active(user)
    elif user.role == RemoteUser.Roles.PROPRIETAIRE:
        quota = settings.LISTING_PROPRIETAIRE_FREE_DAILY_QUOTA
        used = daily_published_count(user)
        payload["daily_quota"] = quota
        payload["daily_used"] = used
        payload["daily_remaining"] = max(0, quota - used)

    return payload
