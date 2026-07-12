from rest_framework.permissions import BasePermission


class IsVerifiedUser(BasePermission):
    """
    Permission personnalisée pour vérifier si un utilisateur peut publier des annonces.
    
    Logique:
    - Les locataires ont toujours accès (pas besoin de vérification)
    - Les propriétaires et agences doivent avoir verification_status == 'verifie'
    """
    message = "Votre compte est en attente de vérification par un administrateur."

    def has_permission(self, request, view):
        # L'utilisateur doit être authentifié
        if not request.user or not request.user.is_authenticated:
            return False
        
        user = request.user
        
        # Les locataires ont accès libre
        if user.role == 'locataire':
            return True
        
        # Les propriétaires et agences doivent être vérifiés
        if user.role in ['proprietaire', 'agence']:
            return user.verification_status == 'verifie'
        
        # Les admins ont accès complet
        if user.role == 'admin':
            return True
        
        return False


class IsOwnerOrAdmin(BasePermission):
    """
    Permission pour vérifier si l'utilisateur est propriétaire de la ressource ou admin.
    """
    def has_object_permission(self, request, view, obj):
        # Les admins ont accès complet
        if request.user.role == 'admin':
            return True
        
        # L'utilisateur doit être le propriétaire de l'objet
        if hasattr(obj, 'user'):
            return obj.user == request.user
        if hasattr(obj, 'proprietaire'):
            return obj.proprietaire == request.user
        
        return False
