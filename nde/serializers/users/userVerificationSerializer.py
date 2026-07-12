from rest_framework import serializers

from nde.models import RemoteUser, UserVerificationDocument


class UpdateOnboardingSerializer(serializers.Serializer):
    """
    Serializer pour la mise à jour du rôle lors de l'onboarding.
    """
    role = serializers.ChoiceField(
        choices=['locataire', 'proprietaire', 'agence'],
        required=True,
        help_text="Rôle choisi par l'utilisateur lors de l'onboarding"
    )

    def validate_role(self, value):
        """Valide que le rôle est dans les choix autorisés."""
        if value not in ['locataire', 'proprietaire', 'agence']:
            raise serializers.ValidationError("Rôle invalide.")
        return value

    def update(self, instance, validated_data):
        """
        Met à jour l'utilisateur avec le rôle choisi.
        
        Logique métier:
        - Si locataire: is_onboarding_complete = True immédiatement
        - Si propriétaire/agence: verification_status = 'en_attente', is_onboarding_complete reste False
        """
        role = validated_data['role']
        instance.role = role
        
        if role == 'locataire':
            # Locataire : accès immédiat
            instance.is_onboarding_complete = True
            instance.verification_status = RemoteUser.VerificationStatus.AUCUN
        else:
            # Propriétaire/Agence : attente de vérification
            instance.verification_status = RemoteUser.VerificationStatus.EN_ATTENTE
            instance.is_onboarding_complete = False
        
        instance.save()
        return instance


class UserVerificationDocumentSerializer(serializers.ModelSerializer):
    """
    Serializer pour les documents de vérification uploadés par les utilisateurs.
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
        """Valide la taille et le type du fichier."""
        # Taille max : 10 MB
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("La taille du fichier ne doit pas dépasser 10 MB.")
        
        # Extensions autorisées
        allowed_extensions = ['pdf', 'jpg', 'jpeg', 'png']
        ext = value.name.split('.')[-1].lower()
        if ext not in allowed_extensions:
            raise serializers.ValidationError(
                f"Format de fichier non autorisé. Formats acceptés : {', '.join(allowed_extensions)}"
            )
        
        return value

    def create(self, validated_data):
        """
        Crée un document de vérification et met à jour le statut de l'utilisateur.
        """
        user = self.context['request'].user
        validated_data['user'] = user
        
        document = UserVerificationDocument.objects.create(**validated_data)
        
        # Si l'utilisateur est propriétaire/agence et qu'il upload un document,
        # on s'assure que son statut passe à 'en_attente' s'il ne l'était pas déjà
        if user.role in [RemoteUser.Roles.PROPRIETAIRE, RemoteUser.Roles.AGENCE]:
            if user.verification_status == RemoteUser.VerificationStatus.AUCUN:
                user.verification_status = RemoteUser.VerificationStatus.EN_ATTENTE
                user.save()
        
        return document
