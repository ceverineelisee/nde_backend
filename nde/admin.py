from django.contrib import admin
from django.utils.html import format_html
from nde.models import (
    RemoteUser,
    UserVerificationDocument,
    Maison,
    DocumentMaison,
    ContactReveal,
    ContactAccessPayment,
    ListingSubscriptionPayment,
)
from nde.listing_access import start_trial_if_eligible


@admin.register(RemoteUser)
class RemoteUserAdmin(admin.ModelAdmin):
    list_display = ('email', 'name', 'role', 'verification_status', 'is_onboarding_complete', 'created_at')
    list_filter = ('role', 'verification_status', 'is_onboarding_complete', 'is_active')
    search_fields = ('email', 'name')
    readonly_fields = ('id', 'created_at', 'updated_at', 'last_login')
    
    fieldsets = (
        ('Informations de base', {
            'fields': ('id', 'email', 'name', 'phone', 'photo_profil')
        }),
        ('Rôle et Vérification', {
            'fields': ('role', 'verification_status', 'is_onboarding_complete')
        }),
        ('Permissions', {
            'fields': ('is_active', 'deactivation_reason', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Dates', {
            'fields': (
                'created_at', 'updated_at', 'last_login',
                'contact_subscription_until',
                'listing_subscription_until', 'listing_trial_used',
            )
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related()
    
    actions = ['approve_users', 'reject_users']
    
    def approve_users(self, request, queryset):
        """Action pour approuver les utilisateurs sélectionnés."""
        eligible_ids = list(queryset.filter(
            role__in=['proprietaire', 'agence'],
            verification_status='en_attente'
        ).values_list('id', flat=True))
        updated = RemoteUser.objects.filter(id__in=eligible_ids).update(
            verification_status='verifie', is_onboarding_complete=True
        )
        for user in RemoteUser.objects.filter(id__in=eligible_ids, role='agence'):
            start_trial_if_eligible(user)
        self.message_user(request, f'{updated} utilisateur(s) approuvé(s) avec succès.')
    approve_users.short_description = "Approuver les utilisateurs sélectionnés"
    
    def reject_users(self, request, queryset):
        """Action pour rejeter les utilisateurs sélectionnés."""
        updated = queryset.filter(
            role__in=['proprietaire', 'agence'],
            verification_status='en_attente'
        ).update(verification_status='rejete')
        self.message_user(request, f'{updated} utilisateur(s) rejeté(s).')
    reject_users.short_description = "Rejeter les utilisateurs sélectionnés"


@admin.register(UserVerificationDocument)
class UserVerificationDocumentAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'document_type', 'status', 'uploaded_at', 'file_link')
    list_filter = ('document_type', 'status', 'uploaded_at')
    search_fields = ('user__email', 'user__name')
    readonly_fields = ('id', 'uploaded_at', 'user', 'file')
    
    fieldsets = (
        ('Informations du document', {
            'fields': ('id', 'user', 'document_type', 'file')
        }),
        ('Statut de vérification', {
            'fields': ('status', 'notes', 'reviewed_at', 'reviewer')
        }),
        ('Dates', {
            'fields': ('uploaded_at',)
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Email utilisateur'
    
    def file_link(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">Voir le fichier</a>', obj.file.url)
        return '-'
    file_link.short_description = 'Fichier'
    
    actions = ['approve_documents', 'reject_documents']
    
    def approve_documents(self, request, queryset):
        """Action pour approuver les documents sélectionnés."""
        updated = queryset.filter(status='en_attente').update(
            status='valide',
            reviewer=request.user,
            reviewed_at=admin.models.timezone.now()
        )
        
        # Vérifier si l'utilisateur a tous ses documents validés
        for doc in queryset:
            user = doc.user
            all_docs_valid = not user.verification_documents.filter(
                status__in=['en_attente', 'rejete']
            ).exists()
            
            if all_docs_valid and user.verification_documents.filter(status='valide').exists():
                user.verification_status = 'verifie'
                user.is_onboarding_complete = True
                user.save()
        
        self.message_user(request, f'{updated} document(s) approuvé(s).')
    approve_documents.short_description = "Approuver les documents sélectionnés"
    
    def reject_documents(self, request, queryset):
        """Action pour rejeter les documents sélectionnés."""
        updated = queryset.filter(status='en_attente').update(
            status='rejete',
            reviewer=request.user,
            reviewed_at=admin.models.timezone.now()
        )
        self.message_user(request, f'{updated} document(s) rejeté(s).')
    reject_documents.short_description = "Rejeter les documents sélectionnés"


@admin.register(Maison)
class MaisonAdmin(admin.ModelAdmin):
    list_display = ('titre', 'proprietaire_email', 'ville', 'prix_location', 'statut', 'date_publication')
    list_filter = ('statut', 'ville', 'created_at')
    search_fields = ('titre', 'proprietaire__email', 'ville', 'adresse')
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Informations de base', {
            'fields': ('id', 'proprietaire', 'titre', 'description')
        }),
        ('Localisation', {
            'fields': ('adresse', 'ville', 'code_postal')
        }),
        ('Prix et publication', {
            'fields': ('prix_location', 'statut', 'date_publication', 'raison_rejet')
        }),
        ('Dates', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def proprietaire_email(self, obj):
        return obj.proprietaire.email
    proprietaire_email.short_description = 'Propriétaire'


@admin.register(ContactReveal)
class ContactRevealAdmin(admin.ModelAdmin):
    list_display = ("user", "maison", "created_at")
    search_fields = ("user__email", "maison__titre")


@admin.register(ContactAccessPayment)
class ContactAccessPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "merchant_reference",
        "user",
        "amount_xaf",
        "status",
        "completed_at",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("merchant_reference", "user__email")


@admin.register(ListingSubscriptionPayment)
class ListingSubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "merchant_reference",
        "user",
        "amount_xaf",
        "status",
        "completed_at",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("merchant_reference", "user__email")


@admin.register(DocumentMaison)
class DocumentMaisonAdmin(admin.ModelAdmin):
    list_display = ('maison', 'type_document', 'statut', 'date_soumission')
    list_filter = ('type_document', 'statut', 'date_soumission')
    search_fields = ('maison__titre',)
    readonly_fields = ('id', 'date_soumission', 'maison', 'fichier')
