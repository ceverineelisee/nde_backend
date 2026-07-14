from django.urls import path, include
from rest_framework.routers import DefaultRouter

from nde.view.views import (
    GoogleLogin,
    EmailLoginView,
    UpdateOnboardingView,
    DocumentUploadView,
    UserDocumentsView,
    UpdateProfileView,
    AcceptTermsView,
    ForgotPasswordView,
    ResetPasswordView,
    ChangePasswordView,
)
from nde.view.admin_views import (
    AdminDashboardStatsView,
    AdminBillingStatsView,
    AdminBillingTransactionsView,
    AdminUsersListView,
    AdminCreateAdminView,
    AdminUserDetailView,
    AdminVerifyUserView,
    AdminToggleUserActiveView,
    AdminDocumentsListView,
    AdminMaisonsListView,
    AdminCommentsListView,
    AdminRemoveFraudulentMaisonView,
)
from nde.view.public_views import (
    PublicMaisonsListView,
    PublicMaisonsCarteView,
    PublicMaisonDetailView,
    PublicVillesListView,
)
from nde.view.payment_views import (
    ContactAccessStatusView,
    ContactAccessKPayInitView,
    ContactAccessKPayReturnView,
    ContactAccessKPayWebhookView,
)
from nde.view.listing_payment_views import (
    ListingAccessStatusView,
    ListingSubscriptionKPayInitView,
    ListingSubscriptionKPayReturnView,
)
from nde.view.comment_views import (
    MaisonCommentairesView,
    CommentaireDeleteView,
)
from nde.view.owner_views import (
    GeocodePreviewView,
    OwnerDashboardStatsView,
    OwnerMaisonsListView,
    OwnerMaisonDetailView,
    OwnerMaisonPublishView,
    OwnerMaisonUnpublishView,
    OwnerMaisonPhotosView,
    OwnerMaisonPhotoDeleteView,
    OwnerNotificationsListView,
    OwnerNotificationReadView,
)

router = DefaultRouter()

custom_urlpatterns = [
    path("auth/google/", GoogleLogin.as_view(), name="google-login"),
    path("auth/login/", EmailLoginView.as_view(), name="email-login"),
    path("auth/password-reset/", ForgotPasswordView.as_view(), name="password-reset"),
    path("auth/password-reset/confirm/", ResetPasswordView.as_view(), name="password-reset-confirm"),
    path("auth/change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("update-onboarding/", UpdateOnboardingView.as_view(), name="update-onboarding"),
    path("verification/upload/", DocumentUploadView.as_view(), name="document-upload"),
    path("verification/documents/", UserDocumentsView.as_view(), name="user-documents"),
    path("profile/", UpdateProfileView.as_view(), name="update-profile"),
    path("accept-terms/", AcceptTermsView.as_view(), name="accept-terms"),
    path(
        "me/contact-access/",
        ContactAccessStatusView.as_view(),
        name="contact-access-status",
    ),
    path(
        "payments/kpay/init/",
        ContactAccessKPayInitView.as_view(),
        name="kpay-contact-init",
    ),
    path(
        "payments/kpay/webhook/",
        ContactAccessKPayWebhookView.as_view(),
        name="kpay-contact-webhook",
    ),
    path(
        "payments/kpay/return/",
        ContactAccessKPayReturnView.as_view(),
        name="kpay-contact-return",
    ),
    path(
        "me/listing-access/",
        ListingAccessStatusView.as_view(),
        name="listing-access-status",
    ),
    path(
        "payments/kpay/listing/init/",
        ListingSubscriptionKPayInitView.as_view(),
        name="kpay-listing-init",
    ),
    path(
        "payments/kpay/listing/return/",
        ListingSubscriptionKPayReturnView.as_view(),
        name="kpay-listing-return",
    ),

    # Admin
    path("admin/stats/", AdminDashboardStatsView.as_view(), name="admin-stats"),
    path("admin/billing/stats/", AdminBillingStatsView.as_view(), name="admin-billing-stats"),
    path("admin/billing/transactions/", AdminBillingTransactionsView.as_view(), name="admin-billing-transactions"),
    path("admin/users/", AdminUsersListView.as_view(), name="admin-users"),
    path("admin/users/create-admin/", AdminCreateAdminView.as_view(), name="admin-create-admin"),
    path("admin/users/<uuid:user_id>/", AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("admin/users/<uuid:user_id>/verify/", AdminVerifyUserView.as_view(), name="admin-verify-user"),
    path("admin/users/<uuid:user_id>/toggle-active/", AdminToggleUserActiveView.as_view(), name="admin-toggle-active"),
    path("admin/documents/", AdminDocumentsListView.as_view(), name="admin-documents"),
    path("admin/maisons/", AdminMaisonsListView.as_view(), name="admin-maisons"),
    path("admin/maisons/<uuid:maison_id>/remove-fraud/", AdminRemoveFraudulentMaisonView.as_view(), name="admin-remove-fraudulent-maison"),
    path("admin/commentaires/", AdminCommentsListView.as_view(), name="admin-comments"),

    # Propriétaire / Agence
    path("owner/geocode-preview/", GeocodePreviewView.as_view(), name="owner-geocode-preview"),
    path("owner/stats/", OwnerDashboardStatsView.as_view(), name="owner-stats"),
    path("owner/maisons/", OwnerMaisonsListView.as_view(), name="owner-maisons"),
    path("owner/maisons/<uuid:maison_id>/", OwnerMaisonDetailView.as_view(), name="owner-maison-detail"),
    path("owner/maisons/<uuid:maison_id>/publish/", OwnerMaisonPublishView.as_view(), name="owner-maison-publish"),
    path("owner/maisons/<uuid:maison_id>/unpublish/", OwnerMaisonUnpublishView.as_view(), name="owner-maison-unpublish"),
    path("owner/maisons/<uuid:maison_id>/photos/", OwnerMaisonPhotosView.as_view(), name="owner-maison-photos"),
    path("owner/maisons/<uuid:maison_id>/photos/<uuid:photo_id>/", OwnerMaisonPhotoDeleteView.as_view(), name="owner-maison-photo-delete"),
    path("owner/notifications/", OwnerNotificationsListView.as_view(), name="owner-notifications"),
    path("owner/notifications/<uuid:notification_id>/read/", OwnerNotificationReadView.as_view(), name="owner-notification-read"),

    # Public (accessible sans authentification)
    path("maisons/", PublicMaisonsListView.as_view(), name="public-maisons"),
    path("maisons/carte/", PublicMaisonsCarteView.as_view(), name="public-maisons-carte"),
    path("maisons/<uuid:maison_id>/", PublicMaisonDetailView.as_view(), name="public-maison-detail"),
    path("villes/", PublicVillesListView.as_view(), name="public-villes"),

    # Commentaires
    path("maisons/<uuid:maison_id>/commentaires/", MaisonCommentairesView.as_view(), name="maison-commentaires"),
    path("commentaires/<uuid:commentaire_id>/", CommentaireDeleteView.as_view(), name="commentaire-delete"),
]

urlpatterns = [
    path("", include(router.urls)),
    path("", include(custom_urlpatterns)),
]