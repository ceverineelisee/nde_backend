import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nde.listing_access import listing_access_payload, price_for, subscription_active
from nde.models import ListingSubscriptionPayment, RemoteUser
from nde.kpay_client import (
    KPayConfigurationError,
    KPayRequestError,
    gateway_return_signature_ok,
    gateway_return_timestamp_fresh,
    get_payment_status,
    init_payment_gateway,
)

logger = logging.getLogger(__name__)


class ListingAccessStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(listing_access_payload(request.user))


class ListingSubscriptionKPayInitView(APIView):
    """Crée le paiement local puis initie une session KPay en mode GATEWAY (page hébergée)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.role not in (RemoteUser.Roles.PROPRIETAIRE, RemoteUser.Roles.AGENCE):
            return Response(
                {"detail": "L'abonnement annonces est destiné aux propriétaires et agences."},
                status=403,
            )
        if user.verification_status != RemoteUser.VerificationStatus.VERIFIE:
            return Response(
                {"detail": "Votre compte doit être vérifié avant de souscrire un abonnement."},
                status=403,
            )

        ref = uuid.uuid4().hex[:32]
        payment = ListingSubscriptionPayment.objects.create(
            user=user,
            amount_xaf=price_for(user),
            merchant_reference=ref,
        )

        frontend_base = settings.FRONTEND_PUBLIC_URL.rstrip("/")
        return_url = f"{frontend_base}/owner/subscription"

        try:
            init_body = init_payment_gateway(
                external_id=ref,
                amount_xaf=payment.amount_xaf,
                return_url=return_url,
                cancel_url=return_url,
                description="Abonnement annonces illimitées NDE",
            )
        except KPayConfigurationError as exc:
            payment.status = ListingSubscriptionPayment.Status.FAILED
            payment.init_response = {"error": str(exc)}
            payment.save(update_fields=("status", "init_response", "updated_at"))
            return Response({"detail": str(exc)}, status=503)
        except KPayRequestError as exc:
            payment.status = ListingSubscriptionPayment.Status.FAILED
            payment.init_response = {"error": str(exc)}
            payment.save(update_fields=("status", "init_response", "updated_at"))
            return Response({"detail": str(exc)}, status=502)

        gateway_url = init_body.get("gatewayUrl")
        if not gateway_url:
            payment.status = ListingSubscriptionPayment.Status.FAILED
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


def finalize_listing_after_success(payment_id, payload: dict) -> None:
    days = settings.LISTING_SUBSCRIPTION_DAYS
    now = timezone.now()

    with transaction.atomic():
        pay = (
            ListingSubscriptionPayment.objects.select_for_update()
            .select_related("user")
            .get(pk=payment_id)
        )
        if pay.status == ListingSubscriptionPayment.Status.PAID:
            return

        user = RemoteUser.objects.select_for_update().get(pk=pay.user_id)
        pay.status = ListingSubscriptionPayment.Status.PAID
        pay.completed_at = now
        pay.webhook_payload = payload
        pay.kpay_transaction_id = (_extract_kpay_payment_id(payload) or pay.kpay_transaction_id)[:191]

        base = now
        if user.listing_subscription_until and user.listing_subscription_until > now:
            base = user.listing_subscription_until
        user.listing_subscription_until = base + timedelta(days=days)

        pay.save(
            update_fields=(
                "status",
                "completed_at",
                "webhook_payload",
                "kpay_transaction_id",
                "updated_at",
            )
        )
        user.save(update_fields=("listing_subscription_until", "updated_at"))


def mark_listing_terminal_failure(payment_id, payload: dict) -> None:
    with transaction.atomic():
        pay = ListingSubscriptionPayment.objects.select_for_update().get(pk=payment_id)
        if pay.status == ListingSubscriptionPayment.Status.PAID:
            return
        pay.status = ListingSubscriptionPayment.Status.FAILED
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


class ListingSubscriptionKPayReturnView(APIView):
    """Validation de la redirection de retour passerelle pour l'abonnement annonces."""

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

        payment = ListingSubscriptionPayment.objects.filter(
            merchant_reference=external_id, user=request.user
        ).first()
        if not payment:
            return Response({"detail": "Paiement introuvable."}, status=404)

        if payment.status != ListingSubscriptionPayment.Status.PAID and payment.kpay_transaction_id:
            try:
                remote = get_payment_status(payment.kpay_transaction_id)
            except (KPayConfigurationError, KPayRequestError) as exc:
                logger.warning(
                    "KPay GET /payments/%s (retour passerelle abonnement) échoué : %s",
                    payment.kpay_transaction_id,
                    exc,
                )
                remote = {}
            remote_status = str(remote.get("status") or "").strip().upper()
            if remote_status == "COMPLETED":
                finalize_listing_after_success(payment.id, remote)
            elif remote_status in ("FAILED", "CANCELLED"):
                mark_listing_terminal_failure(payment.id, remote)
            payment.refresh_from_db()

        return Response(
            {
                "merchant_reference": payment.merchant_reference,
                "status": payment.status,
                "subscription_active": subscription_active(request.user),
            }
        )
