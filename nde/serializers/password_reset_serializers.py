"""
Serializers pour le flux de réinitialisation de mot de passe (mot de passe oublié).
"""
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers


class ForgotPasswordSerializer(serializers.Serializer):
    """Demande d'envoi d'un email de réinitialisation."""
    email = serializers.EmailField(required=True)


class ResetPasswordSerializer(serializers.Serializer):
    """Confirmation de réinitialisation avec le uid/token reçus par email."""
    uid = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value


class ChangePasswordSerializer(serializers.Serializer):
    """Changement de mot de passe par un utilisateur déjà connecté."""
    current_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value
