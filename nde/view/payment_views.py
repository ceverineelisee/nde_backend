import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nde.contact_access import subscription_active
from nde.models import ContactAccessPayment, ContactReveal, ListingSubscriptionPayment, RemoteUser
from nde.view.listing_payment_views import (
    finalize_listing_after_success,
    mark_listing_terminal_failure,
)
from nde.kpay_client import (
    KPayConfigurationError,
    KPayRequestError,
    extract_external_id_from_webhook,
    gateway_return_signature_ok,
    gateway_return_timestamp_fresh,
    get_payment_status,
    init_payment_gateway,
    webhook_indicates_success,
    webhook_signature_ok,
    webhook_terminal_status,
)

logger = logging.getLogger(__name__)


class ContactAccessStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        reveal_count = ContactReveal.objects.filter(user=u).count()
        exp = getattr(u, "contact_subscription_until", None)
        return Response(
            {
                "subscription_active": subscription_active(u),
                "subscription_until": exp.isoformat() if exp else None,
                "free_quota": settings.CONTACT_ACCESS_FREE_VIEWS,
                "free_contacts_used": reveal_count,
                "free_contacts_remaining": max(
                    0, settings.CONTACT_ACCESS_FREE_VIEWS - reveal_count
                ),
                "unlock_price_xaf": settings.CONTACT_ACCESS_PRICE_XAF,
            }
        )


class ContactAccessKPayInitView(APIView):
    """Crée le paiement local puis initie une session KPay en mode GATEWAY (page hébergée)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.role not in (RemoteUser.Roles.LOCATAIRE, RemoteUser.Roles.NON_DEFINI):
            return Response(
                {"detail": "Le déblocage payant est destiné aux comptes locataires."},
                status=403,
            )

        ref = uuid.uuid4().hex[:32]
        payment = ContactAccessPayment.objects.create(
            user=user,
            amount_xaf=settings.CONTACT_ACCESS_PRICE_XAF,
            merchant_reference=ref,
        )

        frontend_base = settings.FRONTEND_PUBLIC_URL.rstrip("/")
        return_url = f"{frontend_base}/profile/payments"

        try:
            init_body = init_payment_gateway(
                external_id=ref,
                amount_xaf=payment.amount_xaf,
                return_url=return_url,
                cancel_url=return_url,
                description=getattr(settings, "KPAY_PAYMENT_DESCRIPTION", "Pass contacts annonces"),
            )
        except KPayConfigurationError as exc:
            payment.status = ContactAccessPayment.Status.FAILED
            payment.init_response = {"error": str(exc)}
            payment.save(update_fields=("status", "init_response", "updated_at"))
            return Response({"detail": str(exc)}, status=503)
        except KPayRequestError as exc:
            payment.status = ContactAccessPayment.Status.FAILED
            payment.init_response = {"error": str(exc)}
            payment.save(update_fields=("status", "init_response", "updated_at"))
            return Response({"detail": str(exc)}, status=502)

        gateway_url = init_body.get("gatewayUrl")
        if not gateway_url:
            payment.status = ContactAccessPayment.Status.FAILED
            payment.init_response = init_body
            payment.save(update_fields=("status", "init_response", "updated_at"))
            return Response({"detail": "Réponse KPay invalide : gatewayUrl manquant."}, status=502)

        payment.init_response = init_body
        payment.kpay_transaction_id = str(init_body.get("id") or "")[:191]
        payment.save(update_fields=("init_response", "kpay_transaction_id", "updated_at"))

        return Response(
            {
                "merchant_reference": ref,
                "gateway_url": gateway_url,
                "expires_at": init_body.get("expiresAt"),
            },
            status=200,
        )


def _extract_kpay_payment_id(wp: dict) -> str:
    for key in ("paymentId", "id"):
        v = wp.get(key)
        if v is not None and not isinstance(v, (dict, list)):
            s = str(v).strip()
            if s:
                return s[:191]
    return ""


def _finalize_after_success(payment_id, payload: dict) -> None:
    days = settings.CONTACT_ACCESS_SUBSCRIPTION_DAYS
    now = timezone.now()

    with transaction.atomic():
        pay = (
            ContactAccessPayment.objects.select_for_update()
            .select_related("user")
            .get(pk=payment_id)
        )
        if pay.status == ContactAccessPayment.Status.PAID:
            return

        user = RemoteUser.objects.select_for_update().get(pk=pay.user_id)
        pay.status = ContactAccessPayment.Status.PAID
        pay.completed_at = now
        pay.webhook_payload = payload
        pay.kpay_transaction_id = (_extract_kpay_payment_id(payload) or pay.kpay_transaction_id)[:191]

        base = now
        if user.contact_subscription_until and user.contact_subscription_until > now:
            base = user.contact_subscription_until
        user.contact_subscription_until = base + timedelta(days=days)

        pay.save(
            update_fields=(
                "status",
                "completed_at",
                "webhook_payload",
                "kpay_transaction_id",
                "updated_at",
            )
        )
        user.save(update_fields=("contact_subscription_until", "updated_at"))


def _mark_terminal_failure(payment_id, payload: dict) -> None:
    with transaction.atomic():
        pay = ContactAccessPayment.objects.select_for_update().get(pk=payment_id)
        if pay.status == ContactAccessPayment.Status.PAID:
            return
        pay.status = ContactAccessPayment.Status.FAILED
        pay.completed_at = timezone.now()
        pay.webhook_payload = payload
        pay.kpay_transaction_id = (_extract_kpay_payment_id(payload) or pay.kpay_transaction_id)[:191]
        pay.save(
            update_fields=(
                "status",
                "completed_at",
                "webhook_payload",
                "kpay_transaction_id",
                "updated_at",
            )
        )


class ContactAccessKPayWebhookView(APIView):
    """
    Source d'autorité du statut final — appelée par KPay en tâche de fond, indépendamment du
    retour navigateur. URL unique côté KPay : ce point d'entrée traite aussi bien le pass
    contacts (locataires) que l'abonnement annonces (propriétaires/agences), en cherchant le
    paiement local correspondant dans les deux tables.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        raw_body = request.body
        header_name = getattr(settings, "KPAY_WEBHOOK_SIGNATURE_HEADER", "X-KPAY-Signature")
        signature = request.headers.get(header_name)

        if not webhook_signature_ok(raw_body, signature):
            return Response(status=403)

        payload_raw = getattr(request, "data", None)
        payload_dict: dict = payload_raw if isinstance(payload_raw, dict) else {}

        external_id = extract_external_id_from_webhook(payload_dict)
        contact_payment = (
            ContactAccessPayment.objects.filter(merchant_reference=external_id).first()
            if external_id
            else None
        )
        listing_payment = (
            ListingSubscriptionPayment.objects.filter(merchant_reference=external_id).first()
            if external_id and not contact_payment
            else None
        )

        if not contact_payment and not listing_payment:
            logger.warning("Webhook KPay sans paiement local (externalId=%s).", external_id)
            return Response(status=200)

        success = webhook_indicates_success(payload_dict)
        terminal_failure = webhook_terminal_status(payload_dict) in ("FAILED", "CANCELLED")

        if contact_payment:
            if success:
                _finalize_after_success(contact_payment.id, payload_dict)
            elif terminal_failure:
                _mark_terminal_failure(contact_payment.id, payload_dict)
        elif listing_payment:
            if success:
                finalize_listing_after_success(listing_payment.id, payload_dict)
            elif terminal_failure:
                mark_listing_terminal_failure(listing_payment.id, payload_dict)

        return Response(status=200)


class ContactAccessKPayReturnView(APIView):
    """
    Validation de la redirection de retour passerelle (returnUrl signée). La signature
    garantit l'authenticité de la redirection, mais seul un statut COMPLETED confirmé via
    GET /payments/:id fait foi pour débloquer l'accès — le webhook reste la source
    d'autorité en tâche de fond (peut avoir déjà traité le paiement avant ce retour).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_param = str(request.query_params.get("status", "")).strip().upper()
        reference = str(request.query_params.get("reference", "")).strip()
        external_id = str(request.query_params.get("externalId", "")).strip()
        ts = str(request.query_params.get("ts", "")).strip()
        sig = str(request.query_params.get("sig", "")).strip()

        if not (status_param and reference and external_id and ts and sig):
            return Response({"detail": "Paramètres de retour KPay incomplets."}, status=400)

        if not gateway_return_timestamp_fresh(ts):
            return Response({"detail": "Lien de retour KPay expiré."}, status=400)

        if not gateway_return_signature_ok(status_param, reference, external_id, ts, sig):
            return Response({"detail": "Signature de retour KPay invalide."}, status=403)

        payment = ContactAccessPayment.objects.filter(
            merchant_reference=external_id, user=request.user
        ).first()
        if not payment:
            return Response({"detail": "Paiement introuvable."}, status=404)

        if payment.status != ContactAccessPayment.Status.PAID and payment.kpay_transaction_id:
            try:
                remote = get_payment_status(payment.kpay_transaction_id)
            except (KPayConfigurationError, KPayRequestError) as exc:
                logger.warning(
                    "KPay GET /payments/%s (retour passerelle) échoué : %s",
                    payment.kpay_transaction_id,
                    exc,
                )
                remote = {}
            remote_status = str(remote.get("status") or "").strip().upper()
            if remote_status == "COMPLETED":
                _finalize_after_success(payment.id, remote)
            elif remote_status in ("FAILED", "CANCELLED"):
                _mark_terminal_failure(payment.id, remote)
            payment.refresh_from_db()

        return Response(
            {
                "merchant_reference": payment.merchant_reference,
                "status": payment.status,
                "subscription_active": subscription_active(request.user),
            }
        )
