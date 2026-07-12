"""
Serializers pour les documents de vérification.
"""
from rest_framework import serializers
from nde.models import UserVerificationDocument


class UserVerificationDocumentSerializer(serializers.ModelSerializer):
    """
    Serializer pour les documents de vérification des utilisateurs.
    """
    
    class Meta:
        model = UserVerificationDocument
        fields = (
            'id',
            'document_type',
            'file',
            'status',
            'uploaded_at',
            'reviewed_at',
            'notes',
        )
        read_only_fields = ('id', 'uploaded_at', 'reviewed_at', 'status', 'notes')
    
    def validate_file(self, value):
        """
        Valider le fichier uploadé.
        """
        # Vérifier la taille du fichier (max 10MB)
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("La taille du fichier ne doit pas dépasser 10 MB.")
        
        # Vérifier l'extension
        allowed_extensions = ['pdf', 'jpg', 'jpeg', 'png']
        ext = value.name.split('.')[-1].lower()
        if ext not in allowed_extensions:
            raise serializers.ValidationError(
                f"Extension de fichier non autorisée. Formats acceptés : {', '.join(allowed_extensions)}"
            )
        
        return value


class UpdateOnboardingSerializer(serializers.Serializer):
    """
    Serializer pour la mise à jour du rôle lors de l'onboarding.
    """
    role = serializers.ChoiceField(
        choices=['locataire', 'proprietaire', 'agence'],
        required=True
    )
    
    def validate_role(self, value):
        """
        Valider que le rôle est bien l'un des choix autorisés.
        """
        if value not in ['locataire', 'proprietaire', 'agence']:
            raise serializers.ValidationError("Rôle invalide.")
        return value
