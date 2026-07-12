from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.conf import settings
import firebase_admin
from firebase_admin import messaging

from nde.serializers.users.usersSerializer import RemoteUserSerializer
from nde.serializers.verification_serializers import (
    UserVerificationDocumentSerializer,
    UpdateOnboardingSerializer
)
from nde.serializers.password_reset_serializers import (
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    ChangePasswordSerializer,
)
from nde.models import UserVerificationDocument, RemoteUser
from nde.emails import send_welcome_email, send_password_reset_email

class GoogleLogin(SocialLoginView):
    """
    Endpoint d'authentification Google pour les clients web / mobiles.
    - Crée ou met à jour l'utilisateur RemoteUser.
    - Envoie un mail et une notification push lors de la première connexion.
    """
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client
    permission_classes = [AllowAny]
    callback_url = settings.GOOGLE_OAUTH_CALLBACK_URL

    def post(self, request, *args, **kwargs):
        # Appel à la logique standard de dj-rest-auth
        original_response = super().post(request, *args, **kwargs)

        if original_response.status_code != status.HTTP_200_OK:
            return original_response

        user = request.user
        
        if not user or not user.is_authenticated:
            return original_response

        if not user.name:
            social_account = user.socialaccount_set.filter(provider='google').first()
            if social_account and social_account.extra_data:
                google_name = social_account.extra_data.get('name', '')
                if google_name:
                    user.name = google_name
                    user.save(update_fields=['name'])

        is_new_user = (timezone.now() - user.created_at).total_seconds() < 30

        if is_new_user:
            fcm_token = getattr(user, 'fcm_token', None)
            if fcm_token:
                try:
                    message = messaging.Message(
                        notification=messaging.Notification(
                            title="Bienvenue sur NDE !",
                            body="Votre compte a été créé avec succès.",
                        ),
                        token=fcm_token,
                    )
                    messaging.send(message)
                except Exception as e:
                    print(f"Erreur lors de l'envoi de la notification : {e}")

        user_data = RemoteUserSerializer(user).data
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": user_data,
                "access_token": str(refresh.access_token),
                "refresh_token": str(refresh),
            },
            status=status.HTTP_200_OK,
        )

class EmailLoginView(APIView):
    """Login email/password qui retourne user + JWT tokens."""
    permission_classes = [AllowAny]

    def post(self, request):
        from django.contrib.auth import authenticate
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response(
                {'non_field_errors': ['Email et mot de passe requis.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, email=email, password=password)
        if user is None:
            return Response(
                {'non_field_errors': ['Email ou mot de passe incorrect.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not user.is_active:
            reason = (user.deactivation_reason or '').strip()
            message = f"Ce compte est désactivé. Motif : {reason}" if reason else "Ce compte est désactivé."
            return Response(
                {'non_field_errors': [message]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        refresh = RefreshToken.for_user(user)
        return Response({
            'user': RemoteUserSerializer(user).data,
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
        })


class UpdateOnboardingView(APIView):
    """
    Met à jour le rôle de l'utilisateur (locataire, propriétaire, agence).
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = UpdateOnboardingSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        role = serializer.validated_data['role']
        user = request.user
        is_first_onboarding = user.role == RemoteUser.Roles.NON_DEFINI
        user.role = role

        if role == 'locataire':
            user.is_onboarding_complete = True
            user.verification_status = 'aucun'
        else:
            user.verification_status = 'aucun'
            user.is_onboarding_complete = False

        user.save()

        if is_first_onboarding:
            send_welcome_email(user)

        return Response(RemoteUserSerializer(user).data, status=status.HTTP_200_OK)

class DocumentUploadView(APIView):
    """
    Gère l'upload des documents de vérification pour propriétaires/agences.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request):
        user = request.user
        if user.role not in ['proprietaire', 'agence']:
            return Response(
                {"error": "Accès réservé aux propriétaires et agences."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        agency_name = request.data.get('agency_name', '').strip()
        if user.role == 'agence' and agency_name:
            user.name = agency_name
        
        serializer = UserVerificationDocumentSerializer(data=request.data)
        if serializer.is_valid():
            document = serializer.save(user=user)
            if user.verification_status == 'aucun':
                user.verification_status = 'en_attente'
            user.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserDocumentsView(APIView):
    """
    Récupère la liste des documents uploadés par l'utilisateur.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        documents = UserVerificationDocument.objects.filter(user=request.user)
        serializer = UserVerificationDocumentSerializer(documents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UpdateProfileView(APIView):
    """Met à jour le profil utilisateur (téléphone, nom)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = RemoteUserSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        user = request.user
        allowed = ['phone', 'country_code', 'name']
        for field in allowed:
            if field in request.data:
                setattr(user, field, request.data[field])
        user.save()
        serializer = RemoteUserSerializer(user)
        return Response(serializer.data)


class AcceptTermsView(APIView):
    """Enregistre l'acceptation obligatoire des CGU (idempotent — ne réécrase pas une date déjà fixée)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.terms_accepted_at:
            user.terms_accepted_at = timezone.now()
            user.save(update_fields=['terms_accepted_at', 'updated_at'])
        return Response(RemoteUserSerializer(user).data)


class ForgotPasswordView(APIView):
    """
    Déclenche l'envoi d'un email de réinitialisation de mot de passe.
    Répond toujours avec succès (même si l'email est inconnu) pour éviter l'énumération de comptes.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        user = RemoteUser.objects.filter(email__iexact=email, is_active=True).first()

        if user and user.has_usable_password():
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_link = f"{settings.FRONTEND_PUBLIC_URL}/reset-password?uid={uid}&token={token}"
            send_password_reset_email(user, reset_link)

        return Response(
            {"detail": "Si un compte existe avec cet email, un lien de réinitialisation vient d'être envoyé."},
            status=status.HTTP_200_OK,
        )


class ResetPasswordView(APIView):
    """Confirme la réinitialisation du mot de passe à partir du uid/token reçus par email."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        uid = serializer.validated_data['uid']
        token = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = RemoteUser.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, RemoteUser.DoesNotExist):
            user = None

        if user is None or not default_token_generator.check_token(user, token):
            return Response(
                {'non_field_errors': ['Lien de réinitialisation invalide ou expiré.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save(update_fields=['password'])

        return Response(
            {"detail": "Votre mot de passe a été réinitialisé avec succès."},
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    """Permet à un utilisateur connecté de changer son mot de passe."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        current_password = serializer.validated_data['current_password']
        new_password = serializer.validated_data['new_password']

        if not user.has_usable_password() or not user.check_password(current_password):
            return Response(
                {'current_password': ['Mot de passe actuel incorrect.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save(update_fields=['password'])

        return Response({"detail": "Votre mot de passe a été mis à jour avec succès."})