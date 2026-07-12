import uuid

from cloudinary_storage.storage import RawMediaCloudinaryStorage
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import FileExtensionValidator
from django.db import models
from simple_history.models import HistoricalRecords

from nde.core.models import BaseModel, SoftDeleteManager
from nde.storages import PrivateRawMediaCloudinaryStorage

# Documents KYC sensibles (identité, titres de propriété, KBIS) : delivery Cloudinary privée.
# Pièces jointes de commentaires : publiques mais non-image (doc/xls) — stockage "raw" public.
# None (= stockage par défaut) tant que Cloudinary n'est pas configuré.
_private_doc_storage = PrivateRawMediaCloudinaryStorage() if settings.CLOUDINARY_ENABLED else None
_public_raw_storage = RawMediaCloudinaryStorage() if settings.CLOUDINARY_ENABLED else None


class RemoteUserManager(BaseUserManager):
    """Manager personnalisé pour RemoteUser."""

    def create_user(self, email, name, password=None, **extra_fields):
        if not email:
            raise ValueError("L'adresse email est obligatoire.")
        email = self.normalize_email(email)
        user = self.model(email=email, name=name, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", RemoteUser.Roles.ADMIN)
        if not password:
            raise ValueError("Le super utilisateur doit avoir un mot de passe.")
        return self.create_user(email, name, password, **extra_fields)


class RemoteUser(AbstractBaseUser, PermissionsMixin):
    """Modèle d'utilisateur unique pour l'application (auth + workflow)."""

    class Roles(models.TextChoices):
        LOCATAIRE = "locataire", "Locataire"
        PROPRIETAIRE = "proprietaire", "Propriétaire"
        AGENCE = "agence", "Agence"
        NON_DEFINI = "non_defini", "Non défini"
        ADMIN = "admin", "Administrateur"

    class VerificationStatus(models.TextChoices):
        AUCUN = "aucun", "Aucun"
        EN_ATTENTE = "en_attente", "En attente"
        VERIFIE = "verifie", "Vérifié"
        REJETE = "rejete", "Rejeté"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    fcm_token = models.TextField(blank=True, null=True)
    name = models.CharField(max_length=255)
    role = models.CharField(
        max_length=20,
        choices=Roles.choices,
        default=Roles.NON_DEFINI,
    )
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.AUCUN,
    )
    is_onboarding_complete = models.BooleanField(default=False)
    phone = models.CharField(max_length=20, blank=True)
    country_code = models.CharField(max_length=5, blank=True, default='+237')
    photo_profil = models.ImageField(upload_to="profils/", blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    contact_subscription_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fin de validité du pass contacts (paiement via KPay).",
    )
    listing_subscription_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fin de validité de l'abonnement annonces illimitées (paiement via KPay).",
    )
    listing_trial_used = models.BooleanField(
        default=False,
        help_text="Empêche de relancer l'essai gratuit de 14 jours (agences vérifiées, usage unique).",
    )
    deactivation_reason = models.TextField(
        blank=True,
        default="",
        help_text="Motif affiché à l'utilisateur lorsque son compte est désactivé (is_active=False).",
    )
    terms_accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date d'acceptation des CGU (obligatoire pour utiliser l'application).",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = RemoteUserManager()

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"

    @property
    def can_publish(self):
        """Indique si l'utilisateur peut publier des annonces."""
        if self.role == self.Roles.LOCATAIRE:
            return True
        return self.role in {self.Roles.PROPRIETAIRE, self.Roles.AGENCE} and (
            self.verification_status == self.VerificationStatus.VERIFIE
        )


class UserVerificationDocument(BaseModel):
    """Pièces justificatives liées aux comptes propriétaires / agences."""

    class DocumentType(models.TextChoices):
        IDENTITE = "identite", "Pièce d'identité"
        TITRE_PROPRIETE = "titre_propriete", "Titre de propriété"
        KBIS_AGENCE = "kbis_agence", "KBIS / Registre agence"

    class Status(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        VALIDE = "valide", "Validé"
        REJETE = "rejete", "Rejeté"

    user = models.ForeignKey(
        RemoteUser,
        on_delete=models.CASCADE,
        related_name="verification_documents",
    )
    document_type = models.CharField(max_length=20, choices=DocumentType.choices)
    file = models.FileField(
        upload_to="verification/%Y/%m/",
        storage=_private_doc_storage,
        validators=[
            FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"])
        ],
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.EN_ATTENTE,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(
        RemoteUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_documents",
        limit_choices_to={"role__in": [RemoteUser.Roles.ADMIN]},
    )
    notes = models.TextField(blank=True)

    

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.user.email} - {self.get_document_type_display()}"


class ContactReveal(BaseModel):
    """Première exposition du téléphone pour ce couple (locataire, maison) — utilisé pour le quota gratuit."""

    user = models.ForeignKey(
        RemoteUser,
        on_delete=models.CASCADE,
        related_name="contact_reveals",
    )
    maison = models.ForeignKey(
        "Maison",
        on_delete=models.CASCADE,
        related_name="contact_reveals",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "maison"),
                name="unique_contact_reveal_user_maison",
            )
        ]
        indexes = [
            models.Index(fields=("user", "created_at")),
        ]

    def __str__(self):
        return f"{self.user.email} → {self.maison_id}"


class ContactAccessPayment(BaseModel):
    """Paiement KPay pour débloquer l'accès aux contacts pendant 30 jours."""

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        PAID = "paid", "Payé"
        FAILED = "failed", "Échec"

    user = models.ForeignKey(
        RemoteUser,
        on_delete=models.CASCADE,
        related_name="contact_access_payments",
    )
    amount_xaf = models.PositiveIntegerField()
    merchant_reference = models.CharField(max_length=64, unique=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    kpay_transaction_id = models.CharField(max_length=191, blank=True)
    webhook_payload = models.JSONField(null=True, blank=True)
    init_response = models.JSONField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.merchant_reference} ({self.status})"


class ListingSubscriptionPayment(BaseModel):
    """Paiement KPay pour l'abonnement annonces illimitées (propriétaires/agences)."""

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        PAID = "paid", "Payé"
        FAILED = "failed", "Échec"

    user = models.ForeignKey(
        RemoteUser,
        on_delete=models.CASCADE,
        related_name="listing_subscription_payments",
    )
    amount_xaf = models.PositiveIntegerField()
    merchant_reference = models.CharField(max_length=64, unique=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    kpay_transaction_id = models.CharField(max_length=191, blank=True)
    webhook_payload = models.JSONField(null=True, blank=True)
    init_response = models.JSONField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.merchant_reference} ({self.status})"


class MaisonManager(SoftDeleteManager):
    """Manager qui n'affiche que les biens dont les propriétaires sont vérifiés."""

    def publier_maisons_verifiees(self):
        return self.filter(
            proprietaire__verification_status=RemoteUser.VerificationStatus.VERIFIE,
        )

    class Meta:
        verbose_name = "Gestionnaire de maisons"
        verbose_name_plural = "Gestionnaires de maisons"


class Maison(BaseModel):
    proprietaire = models.ForeignKey(
        RemoteUser,
        on_delete=models.PROTECT,
        related_name="maisons",
        limit_choices_to={"role__in": ["proprietaire", "agence"]},
    )
    titre = models.CharField(max_length=200)
    description = models.TextField()
    prix_location = models.DecimalField(max_digits=10, decimal_places=2)
    adresse = models.CharField(max_length=255)
    ville = models.CharField(max_length=100)
    code_postal = models.CharField(max_length=10)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    STATUT_PUBLICATION = [
        ("brouillon", "Brouillon"),
        ("en_attente", "En attente de validation"),
        ("publiee", "Publiée"),
        ("rejetee", "Rejetée"),
        ("suspendue", "Suspendue"),
    ]

    statut = models.CharField(
        max_length=20,
        choices=STATUT_PUBLICATION,
        default="brouillon",
    )
    date_publication = models.DateTimeField(null=True, blank=True)
    raison_rejet = models.TextField(blank=True)
    views_count = models.PositiveIntegerField(default=0)

    # history = HistoricalRecords()
    objects = MaisonManager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.titre


class OwnerNotification(BaseModel):
    """Notification in-app destinée aux propriétaires/agences."""

    class NotificationType(models.TextChoices):
        MAISON_SUSPENDUE = "maison_suspendue", "Maison suspendue"

    user = models.ForeignKey(
        RemoteUser,
        on_delete=models.CASCADE,
        related_name="owner_notifications",
        limit_choices_to={"role__in": ["proprietaire", "agence"]},
    )
    maison = models.ForeignKey(
        Maison,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    type = models.CharField(
        max_length=40,
        choices=NotificationType.choices,
        default=NotificationType.MAISON_SUSPENDUE,
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    reason = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.title}"


class PhotoMaison(BaseModel):
    """Photos d'une maison."""
    maison = models.ForeignKey(
        Maison,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    image = models.ImageField(
        upload_to="photos_maisons/%Y/%m/",
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])],
    )
    legende = models.CharField(max_length=200, blank=True)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordre", "created_at"]

    def __str__(self):
        return f"Photo {self.ordre} - {self.maison.titre}"


class DocumentMaison(BaseModel):
    """Documents spécifiques à chaque maison."""

    TYPE_DOCUMENT_MAISON = [
        ("titre_propriete", "Titre de propriété de cette maison"),
        ("acte_vente", "Acte de vente de cette maison"),
        ("mandat_gestion", "Mandat de gestion (si agence)"),
        ("autorisation_location", "Autorisation de location"),
        ("diagnostic_performance", "Diagnostic de performance énergétique"),
        ("certificat_conformite", "Certificat de conformité"),
        ("assurance_habitation", "Assurance habitation"),
        ("taxe_habitation", "Taxe d'habitation"),
        ("autre", "Autre document"),
    ]

    STATUT_DOCUMENT = [
        ("en_attente", "En attente"),
        ("valide", "Validé"),
        ("rejete", "Rejeté"),
        ("expire", "Expiré"),
    ]

    maison = models.ForeignKey(
        Maison,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    type_document = models.CharField(max_length=50, choices=TYPE_DOCUMENT_MAISON)
    fichier = models.FileField(
        upload_to="documents_maisons/%Y/%m/",
        storage=_private_doc_storage,
        validators=[
            FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"])
        ],
    )
    numero_document = models.CharField(max_length=100, blank=True)
    date_emission = models.DateField(null=True, blank=True)
    date_expiration = models.DateField(null=True, blank=True)

    statut = models.CharField(
        max_length=20,
        choices=STATUT_DOCUMENT,
        default="en_attente",
    )
    commentaire = models.TextField(blank=True)

    date_soumission = models.DateTimeField(auto_now_add=True)
    date_verification = models.DateTimeField(null=True, blank=True)
    verifie_par = models.ForeignKey(
        RemoteUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_maisons_verifies",
        limit_choices_to={"role__in": ["admin"]},
    )

    class Meta:
        ordering = ["-date_soumission"]

    def __str__(self):
        return f"{self.get_type_document_display()} - {self.maison.titre}"


class Commentaire(BaseModel):
    """Commentaire sur une maison, visible publiquement."""
    maison = models.ForeignKey(
        Maison,
        on_delete=models.CASCADE,
        related_name="commentaires",
    )
    auteur = models.ForeignKey(
        RemoteUser,
        on_delete=models.CASCADE,
        related_name="commentaires",
    )
    contenu = models.TextField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.auteur.name} - {self.maison.titre}"


class PieceJointeCommentaire(models.Model):
    """Fichier joint à un commentaire."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    commentaire = models.ForeignKey(
        Commentaire,
        on_delete=models.CASCADE,
        related_name="pieces_jointes",
    )
    fichier = models.FileField(
        upload_to="commentaires/%Y/%m/",
        storage=_public_raw_storage,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf", "jpg", "jpeg", "png", "doc", "docx", "xls", "xlsx"]
            )
        ],
    )
    nom_fichier = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return self.nom_fichier

