"""Quota d'accès aux coordonnées (locataires) et pass KPay (Mobile Money)."""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from nde.models import ContactReveal, Maison, RemoteUser


def _subscription_until(user):
    exp = getattr(user, "contact_subscription_until", None)
    return exp if exp else None


def subscription_active(user) -> bool:
    exp = _subscription_until(user)
    return bool(exp and exp > timezone.now())


def _tenant_quota_applies(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "role", "") == RemoteUser.Roles.ADMIN:
        return False
    if getattr(user, "role", "") in (RemoteUser.Roles.PROPRIETAIRE, RemoteUser.Roles.AGENCE):
        return False
    return getattr(user, "role", "") in (
        RemoteUser.Roles.LOCATAIRE,
        RemoteUser.Roles.NON_DEFINI,
    )


def phone_may_be_shown(request_user, maison: Maison) -> bool:
    if not getattr(request_user, "is_authenticated", False):
        return False
    if maison.proprietaire_id == request_user.id:
        return True
    if getattr(request_user, "role", "") == RemoteUser.Roles.ADMIN:
        return True
    if getattr(request_user, "role", "") in (
        RemoteUser.Roles.PROPRIETAIRE,
        RemoteUser.Roles.AGENCE,
    ):
        return True
    if subscription_active(request_user):
        return True
    reveals = ContactReveal.objects.filter(user=request_user).count()
    if reveals < settings.CONTACT_ACCESS_FREE_VIEWS:
        return bool((maison.proprietaire.phone or "").strip())
    already = ContactReveal.objects.filter(user=request_user, maison=maison).exists()
    return already


def contact_access_payload(request_user, maison: Maison) -> dict:
    """Résumé pour le frontend (liste détail annonce)."""
    free_quota = settings.CONTACT_ACCESS_FREE_VIEWS

    meta = {
        "phone_visible": False,
        "free_quota": free_quota,
        "free_contacts_used": None,
        "free_contacts_remaining": None,
        "subscription_active": False,
        "subscription_until": None,
        "requires_login": False,
        "requires_payment": False,
        "unlock_price_xaf": settings.CONTACT_ACCESS_PRICE_XAF,
    }

    if not getattr(request_user, "is_authenticated", False):
        meta["requires_login"] = True
        return meta

    if maison.proprietaire_id == request_user.id or getattr(request_user, "role", "") in (
        RemoteUser.Roles.ADMIN,
        RemoteUser.Roles.PROPRIETAIRE,
        RemoteUser.Roles.AGENCE,
    ):
        meta["phone_visible"] = bool((maison.proprietaire.phone or "").strip())
        meta["subscription_active"] = subscription_active(request_user)
        exp = _subscription_until(request_user)
        meta["subscription_until"] = exp.isoformat() if exp else None
        return meta

    proprietor_phone = (maison.proprietaire.phone or "").strip()

    sub_ok = subscription_active(request_user)
    meta["subscription_active"] = sub_ok
    exp = _subscription_until(request_user)
    if exp:
        meta["subscription_until"] = exp.isoformat()

    reveals = ContactReveal.objects.filter(user=request_user)
    distinct = reveals.count()

    meta["free_contacts_used"] = distinct
    meta["free_contacts_remaining"] = max(0, free_quota - distinct)

    if sub_ok:
        meta["phone_visible"] = bool(proprietor_phone)
        return meta

    if reveals.filter(maison=maison).exists():
        meta["phone_visible"] = bool(proprietor_phone)
        return meta

    if distinct < free_quota:
        meta["phone_visible"] = bool(proprietor_phone)
        return meta

    meta["requires_payment"] = bool(proprietor_phone)
    meta["free_contacts_remaining"] = 0
    return meta


def register_contact_reveal(request_user, maison: Maison) -> None:
    """Enregistre une première exposition des coordonnées (quota locataires)."""
    if not getattr(request_user, "is_authenticated", False):
        return
    if maison.proprietaire_id == request_user.id:
        return
    if not _tenant_quota_applies(request_user):
        return
    if subscription_active(request_user):
        return
    if not (maison.proprietaire.phone or "").strip():
        return
    ContactReveal.objects.get_or_create(user=request_user, maison=maison)
