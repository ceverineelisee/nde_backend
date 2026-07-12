"""
Client KPay — agrégateur de paiement Mobile Money (https://admin.kpay.site).

Authentification par paire de clés statiques (X-API-Key / X-Secret-Key, pas de
renouvellement de secret contrairement à MyPVit). Flux GATEWAY : POST /api/v1/payments/init
sans phoneNumber/provider, avec returnUrl/cancelUrl ; KPay renvoie une gatewayUrl vers
laquelle rediriger le client. Statut définitif via webhook (HMAC-SHA256 sur le corps brut) ;
la redirection de retour (returnUrl) est elle-même signée et sert de complément UX.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class KPayConfigurationError(RuntimeError):
    pass


class KPayRequestError(RuntimeError):
    pass


def _base_url() -> str:
    return (getattr(settings, "KPAY_API_BASE_URL", "") or "").rstrip("/")


def _auth_headers() -> dict[str, str]:
    api_key = (getattr(settings, "KPAY_API_KEY", "") or "").strip()
    secret_key = (getattr(settings, "KPAY_SECRET_KEY", "") or "").strip()
    if not api_key or not secret_key:
        raise KPayConfigurationError(
            "Configurez KPAY_API_KEY et KPAY_SECRET_KEY (tableau de bord KPay, "
            "préfixes kpay_test_/sk_test_ en sandbox ou kpay_live_/sk_live_ en production)."
        )
    return {
        "X-API-Key": api_key,
        "X-Secret-Key": secret_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _timeout() -> int:
    return getattr(settings, "KPAY_HTTP_TIMEOUT_SECONDS", 30)


def _parse_json(resp: requests.Response) -> Any:
    try:
        return resp.json() if resp.content else {}
    except ValueError:
        return {}


def init_payment_gateway(
    external_id: str,
    amount_xaf: int,
    return_url: str,
    cancel_url: str | None = None,
    description: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    POST /api/v1/payments/init en mode GATEWAY (page de paiement hébergée par KPay).
    Ne PAS transmettre phoneNumber/paymentMethod/customerName — interdits en GATEWAY.
    """
    base = _base_url()
    if not base:
        raise KPayConfigurationError("Configurez KPAY_API_BASE_URL (ex. https://admin.kpay.site).")

    payload: dict[str, Any] = {
        "amount": int(amount_xaf),
        "externalId": external_id.strip(),
        "returnUrl": return_url.strip(),
    }
    if cancel_url:
        payload["cancelUrl"] = cancel_url.strip()
    if description:
        payload["description"] = description[:200]
    if metadata:
        payload["metadata"] = metadata

    resp = requests.post(
        f"{base}/api/v1/payments/init",
        json=payload,
        headers=_auth_headers(),
        timeout=_timeout(),
    )
    body = _parse_json(resp)
    if not isinstance(body, dict):
        body = {"raw_text": str(body)[:2000]}

    if not resp.ok:
        logger.error("KPay /payments/init (gateway) HTTP %s: %s", resp.status_code, body)
        raise KPayRequestError(body.get("message") or str(body)[:500])

    return body


def get_payment_status(payment_id: str) -> dict[str, Any]:
    """GET /api/v1/payments/:id — complément de secours au webhook (source d'autorité)."""
    base = _base_url()
    if not base:
        raise KPayConfigurationError("Configurez KPAY_API_BASE_URL (ex. https://admin.kpay.site).")

    resp = requests.get(
        f"{base}/api/v1/payments/{payment_id}",
        headers=_auth_headers(),
        timeout=_timeout(),
    )
    body = _parse_json(resp)
    if not isinstance(body, dict):
        body = {"raw_text": str(body)[:2000]}

    if not resp.ok:
        logger.error("KPay GET /payments/%s HTTP %s: %s", payment_id, resp.status_code, body)
        raise KPayRequestError(body.get("message") or str(body)[:500])

    return body


def extract_external_id_from_webhook(data: dict[str, Any]) -> str | None:
    val = data.get("externalId")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def webhook_terminal_status(data: dict[str, Any]) -> str:
    return str(data.get("status") or "").strip().upper()


def webhook_indicates_success(data: dict[str, Any]) -> bool:
    return webhook_terminal_status(data) == "COMPLETED"


def webhook_signature_ok(raw_body: bytes, signature_header_value: str | None) -> bool:
    """
    Vérifie l'en-tête X-KPAY-Signature : HMAC-SHA256 (hex) calculé sur le corps JSON BRUT
    avec le secret webhook KPay. À faire AVANT tout traitement du payload.
    """
    secret = (getattr(settings, "KPAY_WEBHOOK_SECRET", "") or "").strip()
    if not secret:
        logger.warning("Webhook KPay : KPAY_WEBHOOK_SECRET non configuré — signature non vérifiée.")
        return True

    if not signature_header_value:
        logger.warning("Webhook KPay : en-tête de signature absent — rejet.")
        return False

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header_value.strip())


def gateway_return_signature_ok(status: str, reference: str, external_id: str, ts: str, sig: str) -> bool:
    """
    Vérifie la redirection de retour passerelle (returnUrl) : chaîne signée
    `status|reference|externalId|ts`, HMAC-SHA256 hex. KPAY_GATEWAY_SECRET si défini,
    sinon repli sur KPAY_SECRET_KEY (le guide KPay ne documente pas de secret distinct).
    """
    secret = (getattr(settings, "KPAY_GATEWAY_SECRET", "") or "").strip() or (
        getattr(settings, "KPAY_SECRET_KEY", "") or ""
    ).strip()
    if not secret or not sig:
        return False
    message = f"{status}|{reference}|{external_id}|{ts}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig.strip())


def gateway_return_timestamp_fresh(ts_ms: str, max_age_seconds: int = 600) -> bool:
    """Anti-rejeu : rejette un retour passerelle dont le `ts` (epoch millisecondes) a plus de 10 minutes."""
    try:
        ts_seconds = int(ts_ms) / 1000.0
    except (TypeError, ValueError):
        return False
    return abs(time.time() - ts_seconds) <= max_age_seconds
