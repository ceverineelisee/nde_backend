from django.core.mail import send_mail
from django.conf import settings


def _get_display_name(user):
    """
    Retourne le nom à afficher dans les emails :
    - Agence : nom complet (nom de l'agence)
    - Propriétaire / Locataire : nom complet (prénom + nom)
    Fallback sur l'email si le nom est vide.
    """
    if user.name:
        return user.name
    return user.email.split('@')[0]


def _base_html(content: str) -> str:
    """Envelope HTML commune pour tous les emails."""
    return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:40px 0">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08)">
  <!-- Header -->
  <tr><td style="background:linear-gradient(135deg,#2563eb,#1d4ed8);padding:32px 40px;text-align:center">
    <h1 style="color:#ffffff;margin:0;font-size:24px;font-weight:700;letter-spacing:-0.5px">NDE Location</h1>
  </td></tr>
  <!-- Body -->
  <tr><td style="padding:40px">{content}</td></tr>
  <!-- Footer -->
  <tr><td style="padding:24px 40px;background:#f8fafc;border-top:1px solid #e2e8f0;text-align:center">
    <p style="margin:0;color:#94a3b8;font-size:12px">&copy; 2026 NDE Location &mdash; Tous droits r\u00e9serv\u00e9s</p>
    <p style="margin:4px 0 0;color:#94a3b8;font-size:11px">Cet email a \u00e9t\u00e9 envoy\u00e9 automatiquement, merci de ne pas y r\u00e9pondre.</p>
    <p style="margin:8px 0 0;font-size:11px">
      <a href="{settings.FRONTEND_PUBLIC_URL}/privacy" style="color:#94a3b8;text-decoration:underline">Politique de confidentialit\u00e9</a>
      &nbsp;&middot;&nbsp;
      <a href="{settings.FRONTEND_PUBLIC_URL}/terms" style="color:#94a3b8;text-decoration:underline">Conditions g\u00e9n\u00e9rales d'utilisation</a>
    </p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


def send_welcome_email(user):
    """
    Email de bienvenue envoyé une fois le rôle choisi (onboarding), donc personnalisé par rôle :
    - Agence : prévenir que la vérification des documents prend 24 à 48h.
    - Propriétaire : bienvenue courte + quota de publications gratuites.
    - Locataire : bienvenue courte, sans étapes d'onboarding (aucune vérification requise).
    """
    name = _get_display_name(user)

    if user.role == 'agence':
        content = f"""
        <h2 style="color:#1e293b;margin:0 0 16px;font-size:22px">Bienvenue, {name} !</h2>
        <p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 20px">
          Votre compte <strong>agence</strong> a bien été créé sur NDE.
        </p>
        <p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 20px">
          Pour commencer à publier vos annonces, envoyez vos documents de vérification (registre /
          KBIS) depuis l'application.
        </p>
        <div style="margin:0 0 24px;padding:16px;background:#eff6ff;border-radius:12px;border-left:4px solid #2563eb">
          <p style="margin:0;color:#1e40af;font-size:14px">
            &#9201; La vérification de vos documents prend généralement <strong>24 à 48h</strong>.
            Vous recevrez un email dès que votre compte sera approuvé.
          </p>
        </div>
        <p style="color:#475569;font-size:15px;line-height:1.7;margin:0">
          À très bientôt sur NDE Location !
        </p>
        """
    elif user.role == 'proprietaire':
        content = f"""
        <h2 style="color:#1e293b;margin:0 0 16px;font-size:22px">Bienvenue, {name} !</h2>
        <p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 20px">
          Votre compte <strong>propriétaire</strong> a bien été créé sur NDE.
        </p>
        <div style="margin:0 0 24px;padding:16px;background:#eff6ff;border-radius:12px;border-left:4px solid #2563eb">
          <p style="margin:0;color:#1e40af;font-size:14px">
            Une fois votre compte vérifié, vous pourrez publier
            <strong>{settings.LISTING_PROPRIETAIRE_FREE_DAILY_QUOTA} annonces gratuites par jour</strong>.
          </p>
        </div>
        <p style="color:#475569;font-size:15px;line-height:1.7;margin:0">
          À très bientôt sur NDE Location !
        </p>
        """
    else:
        content = f"""
        <h2 style="color:#1e293b;margin:0 0 16px;font-size:22px">Bienvenue, {name} !</h2>
        <p style="color:#475569;font-size:15px;line-height:1.7;margin:0">
          Votre compte est prêt. Parcourez dès maintenant les annonces disponibles et trouvez
          votre prochain logement sur NDE Location !
        </p>
        """

    html = _base_html(content)

    try:
        send_mail(
            subject="Bienvenue sur NDE Location !",
            message=f"Bienvenue {name} ! Votre compte NDE Location a été créé avec succès.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html,
            fail_silently=True,
        )
    except Exception as e:
        print(f"Erreur envoi email bienvenue: {e}")


def send_verification_approved_email(user):
    """Email envoyé quand le compte propriétaire/agence est approuvé."""
    name = _get_display_name(user)
    role_label = 'propriétaire' if user.role == 'proprietaire' else 'agence'

    content = f"""
    <h2 style="color:#1e293b;margin:0 0 16px;font-size:22px">Félicitations, {name} !</h2>
    <div style="text-align:center;margin:0 0 24px">
      <div style="display:inline-block;width:64px;height:64px;background:#dcfce7;border-radius:50%;line-height:64px;text-align:center">
        <span style="font-size:32px">&#10003;</span>
      </div>
    </div>
    <p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 20px">
      Votre compte <strong>{role_label}</strong> a été <strong style="color:#16a34a">vérifié et approuvé</strong> 
      par notre équipe d'administration.
    </p>
    <p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 20px">
      Vous avez maintenant accès à toutes les fonctionnalités de la plateforme :
    </p>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px">
      <tr><td style="padding:12px 16px;background:#f0fdf4;border-radius:12px;border-left:4px solid #16a34a">
        <p style="margin:0;color:#166534;font-size:14px">&#8226; Publier vos biens immobiliers</p>
      </td></tr>
      <tr><td style="height:8px"></td></tr>
      <tr><td style="padding:12px 16px;background:#f0fdf4;border-radius:12px;border-left:4px solid #16a34a">
        <p style="margin:0;color:#166534;font-size:14px">&#8226; Gérer vos annonces depuis votre dashboard</p>
      </td></tr>
      <tr><td style="height:8px"></td></tr>
      <tr><td style="padding:12px 16px;background:#f0fdf4;border-radius:12px;border-left:4px solid #16a34a">
        <p style="margin:0;color:#166534;font-size:14px">&#8226; Recevoir des demandes de location</p>
      </td></tr>
    </table>
    <p style="color:#475569;font-size:15px;line-height:1.7;margin:0">
      Connectez-vous dès maintenant pour commencer !
    </p>
    """
    html = _base_html(content)

    try:
        send_mail(
            subject="Votre compte a été approuvé ! - NDE Location",
            message=f"Félicitations {name} ! Votre compte {role_label} a été vérifié et approuvé.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html,
            fail_silently=True,
        )
    except Exception as e:
        print(f"Erreur envoi email approbation: {e}")


def send_verification_rejected_email(user, notes=''):
    """Email envoyé quand le compte propriétaire/agence est rejeté."""
    name = _get_display_name(user)
    role_label = 'propriétaire' if user.role == 'proprietaire' else 'agence'

    notes_block = ''
    if notes:
        notes_block = f"""
        <div style="margin:0 0 24px;padding:16px;background:#fef2f2;border-radius:12px;border-left:4px solid #dc2626">
          <p style="margin:0 0 4px;color:#991b1b;font-size:13px;font-weight:600">Motif du rejet :</p>
          <p style="margin:0;color:#991b1b;font-size:14px">{notes}</p>
        </div>
        """

    content = f"""
    <h2 style="color:#1e293b;margin:0 0 16px;font-size:22px">Bonjour, {name}</h2>
    <p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 20px">
      Après examen de vos documents, votre demande de vérification en tant que 
      <strong>{role_label}</strong> n'a malheureusement <strong style="color:#dc2626">pas pu être approuvée</strong>.
    </p>
    {notes_block}
    <p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 20px">
      <strong>Que faire maintenant ?</strong>
    </p>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px">
      <tr><td style="padding:12px 16px;background:#fff7ed;border-radius:12px;border-left:4px solid #ea580c">
        <p style="margin:0;color:#9a3412;font-size:14px"><strong>1.</strong> Vérifiez que vos documents sont lisibles et valides</p>
      </td></tr>
      <tr><td style="height:8px"></td></tr>
      <tr><td style="padding:12px 16px;background:#fff7ed;border-radius:12px;border-left:4px solid #ea580c">
        <p style="margin:0;color:#9a3412;font-size:14px"><strong>2.</strong> Soumettez à nouveau vos documents depuis l'application</p>
      </td></tr>
      <tr><td style="height:8px"></td></tr>
      <tr><td style="padding:12px 16px;background:#fff7ed;border-radius:12px;border-left:4px solid #ea580c">
        <p style="margin:0;color:#9a3412;font-size:14px"><strong>3.</strong> Notre équipe réexaminera votre dossier rapidement</p>
      </td></tr>
    </table>
    <p style="color:#475569;font-size:15px;line-height:1.7;margin:0">
      Si vous pensez qu'il s'agit d'une erreur, n'hésitez pas à nous contacter.
    </p>
    """
    html = _base_html(content)

    try:
        send_mail(
            subject="Vérification non approuvée - NDE Location",
            message=f"Bonjour {name}, votre demande de vérification en tant que {role_label} n'a pas été approuvée.{' Motif: ' + notes if notes else ''}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html,
            fail_silently=True,
        )
    except Exception as e:
        print(f"Erreur envoi email rejet: {e}")


def send_listing_removed_email(user, maison, reason=''):
    """Email envoyé quand une annonce est retirée par un administrateur."""
    name = _get_display_name(user)
    reason_text = (reason or '').strip()

    reason_block = ''
    if reason_text:
        reason_block = f"""
        <div style="margin:0 0 24px;padding:16px;background:#fef2f2;border-radius:12px;border-left:4px solid #dc2626">
          <p style="margin:0 0 4px;color:#991b1b;font-size:13px;font-weight:600">Motif :</p>
          <p style="margin:0;color:#991b1b;font-size:14px">{reason_text}</p>
        </div>
        """

    content = f"""
    <h2 style="color:#1e293b;margin:0 0 16px;font-size:22px">Bonjour, {name}</h2>
    <p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 20px">
      Votre annonce <strong>{maison.titre}</strong> a été <strong style="color:#dc2626">retirée</strong> par l'équipe d'administration
      car elle a été jugée potentiellement frauduleuse.
    </p>
    {reason_block}
    <p style="color:#475569;font-size:15px;line-height:1.7;margin:0">
      Vous pouvez corriger les informations puis republier une annonce conforme.
    </p>
    """
    html = _base_html(content)

    plain_reason = f" Motif: {reason_text}" if reason_text else ""
    try:
        send_mail(
            subject="Annonce retirée par l'administration - NDE Location",
            message=f"Bonjour {name}, votre annonce '{maison.titre}' a été retirée par l'administration pour suspicion de fraude.{plain_reason}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html,
            fail_silently=True,
        )
    except Exception as e:
        print(f"Erreur envoi email retrait annonce: {e}")
