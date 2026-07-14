from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nde.models import (
    RemoteUser,
    UserVerificationDocument,
    Maison,
    DocumentMaison,
    OwnerNotification,
    ContactAccessPayment,
    ListingSubscriptionPayment,
    Commentaire,
)
from nde.serializers.users.usersSerializer import RemoteUserSerializer
from nde.serializers.admin_serializers import AdminCreateAdminSerializer
from nde.listing_access import start_trial_if_eligible
from nde.view.public_views import haversine_km
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


def _payment_serialize(payment, type_label):
    return {
        'id': str(payment.id),
        'type': type_label,
        'user': {
            'id': str(payment.user_id),
            'name': payment.user.name,
            'email': payment.user.email,
        },
        'amount_xaf': payment.amount_xaf,
        'status': payment.status,
        'status_display': payment.get_status_display(),
        'merchant_reference': payment.merchant_reference,
        'kpay_transaction_id': payment.kpay_transaction_id,
        'created_at': payment.created_at,
        'completed_at': payment.completed_at,
    }


class AdminBillingStatsView(APIView):
    """
    Vue d'ensemble de la facturation : chiffre d'affaires (pass contacts + abonnements
    annonces), payé via KPay, agrégé sur l'ensemble et sur les 30/7 derniers jours.
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        seven_days_ago = now - timedelta(days=7)

        contact_paid = ContactAccessPayment.objects.filter(
            status=ContactAccessPayment.Status.PAID
        )
        listing_paid = ListingSubscriptionPayment.objects.filter(
            status=ListingSubscriptionPayment.Status.PAID
        )

        def total_amount(qs):
            return qs.aggregate(total=Sum('amount_xaf'))['total'] or 0

        contact_revenue = total_amount(contact_paid)
        listing_revenue = total_amount(listing_paid)

        revenue_30d = (
            total_amount(contact_paid.filter(completed_at__gte=thirty_days_ago))
            + total_amount(listing_paid.filter(completed_at__gte=thirty_days_ago))
        )
        revenue_7d = (
            total_amount(contact_paid.filter(completed_at__gte=seven_days_ago))
            + total_amount(listing_paid.filter(completed_at__gte=seven_days_ago))
        )

        contact_counts = dict(
            ContactAccessPayment.objects.values_list('status').annotate(c=Count('id')).values_list('status', 'c')
        )
        listing_counts = dict(
            ListingSubscriptionPayment.objects.values_list('status').annotate(c=Count('id')).values_list('status', 'c')
        )

        def daily_revenue(qs):
            rows = (
                qs.filter(completed_at__gte=thirty_days_ago)
                .annotate(date=TruncDate('completed_at'))
                .values('date')
                .annotate(total=Sum('amount_xaf'))
            )
            return {r['date']: r['total'] for r in rows}

        contact_daily = daily_revenue(contact_paid)
        listing_daily = daily_revenue(listing_paid)
        all_dates = sorted(set(contact_daily) | set(listing_daily))
        revenue_chart = [
            {
                'date': d.isoformat(),
                'total': (contact_daily.get(d) or 0) + (listing_daily.get(d) or 0),
            }
            for d in all_dates
        ]

        return Response({
            'total_revenue_xaf': contact_revenue + listing_revenue,
            'contact_access_revenue_xaf': contact_revenue,
            'listing_subscription_revenue_xaf': listing_revenue,
            'revenue_30d_xaf': revenue_30d,
            'revenue_7d_xaf': revenue_7d,
            'contact_access_counts': contact_counts,
            'listing_subscription_counts': listing_counts,
            'revenue_chart': revenue_chart,
        })


class AdminBillingTransactionsView(APIView):
    """Liste unifiée et paginée des transactions KPay (pass contacts + abonnements annonces)."""
    permission_classes = [IsAdmin]

    VALID_TYPES = ('contact_access', 'listing_subscription')

    def get(self, request):
        type_filter = request.query_params.get('type')
        status_filter = request.query_params.get('status')
        search = request.query_params.get('search', '').strip()

        if type_filter and type_filter not in self.VALID_TYPES:
            return Response({'error': 'Type invalide.'}, status=status.HTTP_400_BAD_REQUEST)
        valid_statuses = set(ContactAccessPayment.Status.values)
        if status_filter and status_filter not in valid_statuses:
            return Response({'error': 'Statut invalide.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except ValueError:
            page = 1
        try:
            page_size = min(100, max(1, int(request.query_params.get('page_size', 25))))
        except ValueError:
            page_size = 25

        transactions = []

        if type_filter != 'listing_subscription':
            qs = ContactAccessPayment.objects.select_related('user').all()
            if status_filter:
                qs = qs.filter(status=status_filter)
            if search:
                qs = qs.filter(Q(user__name__icontains=search) | Q(user__email__icontains=search))
            transactions.extend(_payment_serialize(p, 'contact_access') for p in qs)

        if type_filter != 'contact_access':
            qs = ListingSubscriptionPayment.objects.select_related('user').all()
            if status_filter:
                qs = qs.filter(status=status_filter)
            if search:
                qs = qs.filter(Q(user__name__icontains=search) | Q(user__email__icontains=search))
            transactions.extend(_payment_serialize(p, 'listing_subscription') for p in qs)

        transactions.sort(key=lambda t: t['created_at'], reverse=True)

        total = len(transactions)
        start_idx = (page - 1) * page_size
        page_items = transactions[start_idx:start_idx + page_size]
        for item in page_items:
            item['created_at'] = item['created_at'].isoformat()
            item['completed_at'] = item['completed_at'].isoformat() if item['completed_at'] else None

        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': page_items,
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


class AdminMaisonsListView(APIView):
    """Liste paginée de toutes les annonces (tous statuts) pour modération admin."""
    permission_classes = [IsAdmin]

    def get(self, request):
        statut_filter = request.query_params.get('statut')
        search = request.query_params.get('search', '').strip()

        valid_statuts = {c[0] for c in Maison.STATUT_PUBLICATION}
        if statut_filter and statut_filter not in valid_statuts:
            return Response({'error': 'Statut invalide.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except ValueError:
            page = 1
        try:
            page_size = min(100, max(1, int(request.query_params.get('page_size', 25))))
        except ValueError:
            page_size = 25

        qs = Maison.objects.select_related('proprietaire').prefetch_related('photos').all()
        if statut_filter:
            qs = qs.filter(statut=statut_filter)
        if search:
            qs = qs.filter(
                Q(titre__icontains=search)
                | Q(ville__icontains=search)
                | Q(proprietaire__name__icontains=search)
                | Q(proprietaire__email__icontains=search)
            )

        total = qs.count()
        start_idx = (page - 1) * page_size
        page_items = qs[start_idx:start_idx + page_size]

        results = []
        for m in page_items:
            first_photo = m.photos.first()
            publication_distance_km = None
            if (
                m.latitude is not None and m.longitude is not None
                and m.publication_latitude is not None and m.publication_longitude is not None
            ):
                publication_distance_km = round(
                    haversine_km(m.latitude, m.longitude, m.publication_latitude, m.publication_longitude),
                    1,
                )
            results.append({
                'id': str(m.id),
                'titre': m.titre,
                'ville': m.ville,
                'adresse': m.adresse,
                'prix_location': str(m.prix_location),
                'statut': m.statut,
                'statut_display': dict(Maison.STATUT_PUBLICATION).get(m.statut, m.statut),
                'raison_rejet': m.raison_rejet,
                'views_count': m.views_count,
                'date_publication': m.date_publication.isoformat() if m.date_publication else None,
                'created_at': m.created_at.isoformat(),
                'photo_principale': (
                    request.build_absolute_uri(first_photo.image.url)
                    if first_photo and first_photo.image else None
                ),
                'latitude': m.latitude,
                'longitude': m.longitude,
                'publication_latitude': m.publication_latitude,
                'publication_longitude': m.publication_longitude,
                'publication_distance_km': publication_distance_km,
                'proprietaire': {
                    'id': str(m.proprietaire_id),
                    'name': m.proprietaire.name,
                    'email': m.proprietaire.email,
                    'role': m.proprietaire.role,
                },
            })

        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': results,
        })


class AdminCommentsListView(APIView):
    """Liste paginée de tous les commentaires (toutes annonces) pour modération admin."""
    permission_classes = [IsAdmin]

    def get(self, request):
        search = request.query_params.get('search', '').strip()
        maison_id = request.query_params.get('maison_id')

        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except ValueError:
            page = 1
        try:
            page_size = min(100, max(1, int(request.query_params.get('page_size', 25))))
        except ValueError:
            page_size = 25

        qs = (
            Commentaire.objects
            .select_related('auteur', 'maison')
            .prefetch_related('pieces_jointes')
            .all()
        )
        if maison_id:
            qs = qs.filter(maison_id=maison_id)
        if search:
            qs = qs.filter(
                Q(contenu__icontains=search)
                | Q(auteur__name__icontains=search)
                | Q(auteur__email__icontains=search)
                | Q(maison__titre__icontains=search)
            )

        total = qs.count()
        start_idx = (page - 1) * page_size
        page_items = qs[start_idx:start_idx + page_size]

        results = []
        for c in page_items:
            results.append({
                'id': str(c.id),
                'contenu': c.contenu,
                'created_at': c.created_at.isoformat(),
                'auteur': {
                    'id': str(c.auteur_id),
                    'name': c.auteur.name,
                    'email': c.auteur.email,
                    'role': c.auteur.role,
                },
                'maison': {
                    'id': str(c.maison_id),
                    'titre': c.maison.titre,
                },
                'pieces_jointes_count': c.pieces_jointes.count(),
            })

        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': results,
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
