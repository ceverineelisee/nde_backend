"""
Serializers réservés aux actions d'administration (création de comptes admin, etc.).
"""
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from nde.models import RemoteUser


class AdminCreateAdminSerializer(serializers.Serializer):
    """Création d'un nouveau compte administrateur par un admin existant."""
    name = serializers.CharField(required=True, max_length=255)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)

    def validate_email(self, value):
        value = value.strip().lower()
        if RemoteUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Un compte existe déjà avec cet email.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value
