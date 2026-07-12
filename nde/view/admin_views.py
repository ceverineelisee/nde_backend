from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nde.models import RemoteUser, UserVerificationDocument, Maison, DocumentMaison, OwnerNotification
from nde.serializers.users.usersSerializer import RemoteUserSerializer
from nde.serializers.admin_serializers import AdminCreateAdminSerializer
from nde.listing_access import start_trial_if_eligible
from nde.emails import (
    send_verification_approved_email,
    send_verification_rejected_email,
    send_listing_removed_email,
)


class IsAdmin(IsAuthenticated):
    """Seuls les admins peuvent accéder."""
    def has_permission(self, request, view):
        return super().has_permission(request, view) and (
            request.user.role == 'admin' or request.user.is_superuser
        )


class IsSuperUser(IsAuthenticated):
    """
    Réservé aux superusers Django (créés via `createsuperuser`, hors app).
    Utilisé pour les actions sensibles d'élévation de privilèges (création d'admins) :
    un compte admin "ordinaire" compromis ne doit pas pouvoir en créer d'autres.
    """
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_superuser


class AdminDashboardStatsView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        seven_days_ago = now - timedelta(days=7)

        total_users = RemoteUser.objects.count()
        new_users_30d = RemoteUser.objects.filter(created_at__gte=thirty_days_ago).count()
        new_users_7d = RemoteUser.objects.filter(created_at__gte=seven_days_ago).count()

        users_by_role = dict(
            RemoteUser.objects.values_list('role').annotate(c=Count('id')).values_list('role', 'c')
        )

        pending_verifications = UserVerificationDocument.objects.filter(status='en_attente').count()
        verified_users = RemoteUser.objects.filter(verification_status='verifie').count()
        rejected_users = RemoteUser.objects.filter(verification_status='rejete').count()
        pending_users = RemoteUser.objects.filter(verification_status='en_attente').count()

        total_maisons = Maison.objects.count()
        maisons_publiees = Maison.objects.filter(statut='publiee').count()
        maisons_en_attente = Maison.objects.filter(statut='en_attente').count()

        registrations_chart = list(
            RemoteUser.objects
            .filter(created_at__gte=thirty_days_ago)
            .annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
            .values('date', 'count')
        )
        for item in registrations_chart:
            item['date'] = item['date'].isoformat()

        recent_users = RemoteUser.objects.order_by('-created_at')[:5]
        recent_users_data = RemoteUserSerializer(recent_users, many=True).data

        return Response({
            'total_users': total_users,
            'new_users_30d': new_users_30d,
            'new_users_7d': new_users_7d,
            'users_by_role': users_by_role,
            'pending_verifications': pending_verifications,
            'verified_users': verified_users,
            'rejected_users': rejected_users,
            'pending_users': pending_users,
            'total_maisons': total_maisons,
            'maisons_publiees': maisons_publiees,
            'maisons_en_attente': maisons_en_attente,
            'registrations_chart': registrations_chart,
            'recent_users': recent_users_data,
        })


class AdminUsersListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        role_filter = request.query_params.get('role')
        verification = request.query_params.get('verification_status')
        search = request.query_params.get('search', '')

        qs = RemoteUser.objects.all().order_by('-created_at')
        if role_filter:
            if role_filter not in RemoteUser.Roles.values:
                return Response({'error': 'Rôle invalide.'}, status=status.HTTP_400_BAD_REQUEST)
            qs = qs.filter(role=role_filter)
        if verification:
            if verification not in RemoteUser.VerificationStatus.values:
                return Response({'error': 'Statut de vérification invalide.'}, status=status.HTTP_400_BAD_REQUEST)
            qs = qs.filter(verification_status=verification)
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(email__icontains=search))

        data = RemoteUserSerializer(qs, many=True).data
        return Response(data)


class AdminCreateAdminView(APIView):
    """
    Crée un nouveau compte administrateur.
    Réservé aux superusers (pas à tout compte role='admin') pour limiter le risque
    de prolifération de comptes admin en cas de compromission d'un compte admin ordinaire.
    """
    permission_classes = [IsSuperUser]

    def post(self, request):
        serializer = AdminCreateAdminSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        user = RemoteUser.objects.create_user(
            email=data['email'],
            name=data['name'],
            password=data['password'],
            role=RemoteUser.Roles.ADMIN,
            is_staff=True,
            is_onboarding_complete=True,
        )

        return Response(RemoteUserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminUserDetailView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, user_id):
        try:
            user = RemoteUser.objects.get(id=user_id)
        except RemoteUser.DoesNotExist:
            return Response({'error': 'Utilisateur introuvable.'}, status=404)

        user_data = RemoteUserSerializer(user).data
        docs = UserVerificationDocument.objects.filter(user=user)
        docs_data = [{
            'id': str(d.id),
            'document_type': d.document_type,
            'document_type_display': d.get_document_type_display(),
            'file': request.build_absolute_uri(d.file.url) if d.file else None,
            'status': d.status,
            'uploaded_at': d.uploaded_at.isoformat(),
            'notes': d.notes,
        } for d in docs]

        maisons = Maison.objects.filter(proprietaire=user)
        maisons_data = [{
            'id': str(m.id),
            'titre': m.titre,
            'ville': m.ville,
            'statut': m.statut,
            'prix_location': str(m.prix_location),
        } for m in maisons]

        return Response({
            'user': user_data,
            'documents': docs_data,
            'maisons': maisons_data,
        })


class AdminVerifyUserView(APIView):
    """Valider ou rejeter un propriétaire/agence."""
    permission_classes = [IsAdmin]

    def post(self, request, user_id):
        action = request.data.get('action')
        notes = request.data.get('notes', '')

        if action not in ('approve', 'reject'):
            return Response({'error': "Action invalide. Utilisez 'approve' ou 'reject'."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            user = RemoteUser.objects.get(id=user_id)
        except RemoteUser.DoesNotExist:
            return Response({'error': 'Utilisateur introuvable.'}, status=404)

        if user.role not in ('proprietaire', 'agence'):
            return Response({'error': 'Seuls les propriétaires et agences peuvent être vérifiés.'},
                            status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        if action == 'approve':
            user.verification_status = 'verifie'
            user.is_onboarding_complete = True
            UserVerificationDocument.objects.filter(user=user, status='en_attente').update(
                status='valide', reviewed_at=now, reviewer=request.user
            )
            user.save()
            start_trial_if_eligible(user)
            send_verification_approved_email(user)
        else:
            user.verification_status = 'rejete'
            UserVerificationDocument.objects.filter(user=user, status='en_attente').update(
                status='rejete', reviewed_at=now, reviewer=request.user, notes=notes
            )
            user.save()
            send_verification_rejected_email(user, notes)

        return Response(RemoteUserSerializer(user).data)


class AdminDocumentsListView(APIView):
    """Liste tous les documents de vérification soumis."""
    permission_classes = [IsAdmin]

    def get(self, request):
        status_filter = request.query_params.get('status')
        role_filter = request.query_params.get('role')
        search = request.query_params.get('search', '')

        qs = UserVerificationDocument.objects.select_related('user').all()

        if status_filter:
            qs = qs.filter(status=status_filter)
        if role_filter:
            qs = qs.filter(user__role=role_filter)
        if search:
            qs = qs.filter(
                Q(user__name__icontains=search) | Q(user__email__icontains=search)
            )

        data = []
        for d in qs:
            data.append({
                'id': str(d.id),
                'document_type': d.document_type,
                'document_type_display': d.get_document_type_display(),
                'file': request.build_absolute_uri(d.file.url) if d.file else None,
                'status': d.status,
                'status_display': d.get_status_display(),
                'uploaded_at': d.uploaded_at.isoformat(),
                'reviewed_at': d.reviewed_at.isoformat() if d.reviewed_at else None,
                'notes': d.notes,
                'user': {
                    'id': str(d.user.id),
                    'name': d.user.name,
                    'email': d.user.email,
                    'role': d.user.role,
                    'verification_status': d.user.verification_status,
                },
            })

        return Response(data)


class AdminToggleUserActiveView(APIView):
    """Activer/désactiver un utilisateur."""
    permission_classes = [IsAdmin]

    def post(self, request, user_id):
        try:
            user = RemoteUser.objects.get(id=user_id)
        except RemoteUser.DoesNotExist:
            return Response({'error': 'Utilisateur introuvable.'}, status=404)

        user.is_active = not user.is_active
        if user.is_active:
            user.deactivation_reason = ''
        else:
            user.deactivation_reason = (request.data.get('reason') or '').strip()
        user.save(update_fields=['is_active', 'deactivation_reason', 'updated_at'])
        return Response({
            'id': str(user.id),
            'is_active': user.is_active,
            'deactivation_reason': user.deactivation_reason,
            'message': f"Utilisateur {'activé' if user.is_active else 'désactivé'}.",
        })


class AdminRemoveFraudulentMaisonView(APIView):
    """Retirer une annonce jugée frauduleuse."""
    permission_classes = [IsAdmin]

    def post(self, request, maison_id):
        reason = (request.data.get('reason') or '').strip()
        if not reason:
            reason = "Annonce retirée par l'administrateur pour suspicion de fraude."

        try:
            maison = Maison.objects.get(id=maison_id)
        except Maison.DoesNotExist:
            return Response({'error': 'Annonce introuvable.'}, status=404)

        maison.statut = 'suspendue'
        maison.date_publication = None
        maison.raison_rejet = reason
        maison.save(update_fields=['statut', 'date_publication', 'raison_rejet', 'updated_at'])

        OwnerNotification.objects.create(
            user=maison.proprietaire,
            maison=maison,
            type=OwnerNotification.NotificationType.MAISON_SUSPENDUE,
            title="Annonce retirée par l'administration",
            message=f"Votre annonce '{maison.titre}' a été retirée pour suspicion de fraude.",
            reason=reason,
        )
        send_listing_removed_email(maison.proprietaire, maison, reason)

        return Response({
            'id': str(maison.id),
            'statut': maison.statut,
            'raison_rejet': maison.raison_rejet,
            'message': 'Annonce retirée pour fraude.',
        })
