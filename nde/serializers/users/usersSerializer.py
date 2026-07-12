from rest_framework import serializers

from nde.models import RemoteUser


class RemoteUserSerializer(serializers.ModelSerializer):
    """
    Sérialiseur principal pour exposer l'utilisateur connecté au front.
    """

    class Meta:
        model = RemoteUser
        fields = (
            "id",
            "email",
            "name",
            "role",
            "verification_status",
            "is_onboarding_complete",
            "phone",
            "country_code",
            "photo_profil",
            "contact_subscription_until",
            "is_active",
            "deactivation_reason",
            "terms_accepted_at",
        )
        read_only_fields = (
            "contact_subscription_until",
            "is_active",
            "deactivation_reason",
            "terms_accepted_at",
        )

