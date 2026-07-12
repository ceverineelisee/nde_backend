from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser

from nde.models import Maison, PhotoMaison, DocumentMaison, RemoteUser, OwnerNotification
from nde.geocoding import geocode_address
from nde.listing_access import can_publish_more, price_for
from nde.upload_validation import validate_uploaded_file


class IsVerifiedOwner(IsAuthenticated):
    """Propriétaire ou agence vérifié(e)."""
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user = request.user
        return (
            user.role in ('proprietaire', 'agence')
            and user.verification_status == 'verifie'
        )


class PhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = PhotoMaison
        fields = ('id', 'url', 'legende', 'ordre')

    def get_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class MaisonSerializer(serializers.ModelSerializer):
    photos_count = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()

    class Meta:
        model = Maison
        fields = (
            'id', 'titre', 'description', 'prix_location',
            'adresse', 'ville', 'code_postal', 'statut',
            'date_publication', 'raison_rejet', 'created_at',
            'photos_count', 'photos', 'latitude', 'longitude',
            'views_count',
        )
        read_only_fields = ('id', 'statut', 'date_publication', 'raison_rejet', 'created_at', 'views_count')

    def get_photos_count(self, obj):
        return obj.photos.count()

    def get_photos(self, obj):
        request = self.context.get('request')
        return PhotoSerializer(obj.photos.all(), many=True, context={'request': request}).data


class MaisonCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Maison
        fields = (
            'titre', 'description', 'prix_location',
            'adresse', 'ville', 'code_postal',
        )


class OwnerDashboardStatsView(APIView):
    permission_classes = [IsVerifiedOwner]

    def get(self, request):
        maisons = Maison.objects.filter(proprietaire=request.user)
        total = maisons.count()
        publiees = maisons.filter(statut='publiee').count()
        brouillons = maisons.filter(statut='brouillon').count()
        total_views = maisons.aggregate(total=Sum('views_count'))['total'] or 0

        maisons_data = MaisonSerializer(
            maisons[:10], many=True, context={'request': request}
        ).data

        return Response({
            'total_maisons': total,
            'publiees': publiees,
            'brouillons': brouillons,
            'total_views': total_views,
            'maisons': maisons_data,
        })


class OwnerMaisonsListView(APIView):
    permission_classes = [IsVerifiedOwner]

    def get(self, request):
        statut = request.query_params.get('statut')
        search = request.query_params.get('search', '')

        qs = Maison.objects.filter(proprietaire=request.user)
        if statut:
            qs = qs.filter(statut=statut)
        if search:
            qs = qs.filter(Q(titre__icontains=search) | Q(ville__icontains=search))

        return Response(
            MaisonSerializer(qs, many=True, context={'request': request}).data
        )

    def post(self, request):
        serializer = MaisonCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        maison = serializer.save(proprietaire=request.user, statut='brouillon')
        coords = geocode_address(maison.adresse, maison.ville, maison.code_postal)
        if coords:
            maison.latitude, maison.longitude = coords
            maison.save(update_fields=['latitude', 'longitude'])
        return Response(
            MaisonSerializer(maison, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class OwnerMaisonDetailView(APIView):
    permission_classes = [IsVerifiedOwner]

    def _get_maison(self, request, maison_id):
        try:
            return Maison.objects.get(id=maison_id, proprietaire=request.user)
        except Maison.DoesNotExist:
            return None

    def get(self, request, maison_id):
        maison = self._get_maison(request, maison_id)
        if not maison:
            return Response({'error': 'Maison introuvable.'}, status=404)

        data = MaisonSerializer(maison, context={'request': request}).data
        return Response(data)

    def put(self, request, maison_id):
        maison = self._get_maison(request, maison_id)
        if not maison:
            return Response({'error': 'Maison introuvable.'}, status=404)
        old_adresse = maison.adresse
        old_ville = maison.ville
        serializer = MaisonCreateSerializer(maison, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        maison.refresh_from_db()
        if maison.adresse != old_adresse or maison.ville != old_ville:
            coords = geocode_address(maison.adresse, maison.ville, maison.code_postal)
            if coords:
                maison.latitude, maison.longitude = coords
                maison.save(update_fields=['latitude', 'longitude'])
        return Response(MaisonSerializer(maison, context={'request': request}).data)

    def delete(self, request, maison_id):
        maison = self._get_maison(request, maison_id)
        if not maison:
            return Response({'error': 'Maison introuvable.'}, status=404)
        maison.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OwnerMaisonPublishView(APIView):
    """Publier directement une maison (pas de validation admin)."""
    permission_classes = [IsVerifiedOwner]

    def post(self, request, maison_id):
        try:
            maison = Maison.objects.get(id=maison_id, proprietaire=request.user)
        except Maison.DoesNotExist:
            return Response({'error': 'Maison introuvable.'}, status=404)

        if maison.statut == 'publiee':
            return Response({'error': 'Cette maison est déjà publiée.'}, status=status.HTTP_400_BAD_REQUEST)

        if not can_publish_more(request.user):
            if request.user.role == RemoteUser.Roles.AGENCE:
                message = (
                    "Votre essai gratuit de 14 jours est terminé. Abonnez-vous "
                    f"({price_for(request.user):,} FCFA/mois) pour continuer à publier."
                ).replace(",", " ")
            else:
                message = (
                    "Vous avez atteint vos 2 publications gratuites du jour. Abonnez-vous "
                    f"({price_for(request.user):,} FCFA/mois) pour publier sans limite."
                ).replace(",", " ")
            return Response({'error': message}, status=status.HTTP_403_FORBIDDEN)

        maison.statut = 'publiee'
        maison.date_publication = timezone.now()
        maison.save()
        return Response(MaisonSerializer(maison, context={'request': request}).data)


class OwnerMaisonUnpublishView(APIView):
    """Dépublier une maison (repasse en brouillon)."""
    permission_classes = [IsVerifiedOwner]

    def post(self, request, maison_id):
        try:
            maison = Maison.objects.get(id=maison_id, proprietaire=request.user)
        except Maison.DoesNotExist:
            return Response({'error': 'Maison introuvable.'}, status=404)

        if maison.statut != 'publiee':
            return Response({'error': 'Cette maison n\'est pas publiée.'}, status=status.HTTP_400_BAD_REQUEST)

        maison.statut = 'brouillon'
        maison.date_publication = None
        maison.save()
        return Response(MaisonSerializer(maison, context={'request': request}).data)


class OwnerMaisonPhotosView(APIView):
    """Upload de photos pour une maison."""
    permission_classes = [IsVerifiedOwner]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, maison_id):
        try:
            maison = Maison.objects.get(id=maison_id, proprietaire=request.user)
        except Maison.DoesNotExist:
            return Response({'error': 'Maison introuvable.'}, status=404)

        photos = PhotoSerializer(
            maison.photos.all(), many=True, context={'request': request}
        ).data
        return Response(photos)

    def post(self, request, maison_id):
        try:
            maison = Maison.objects.get(id=maison_id, proprietaire=request.user)
        except Maison.DoesNotExist:
            return Response({'error': 'Maison introuvable.'}, status=404)

        files = request.FILES.getlist('photos')
        if not files:
            return Response({'error': 'Aucune photo envoyée.'}, status=status.HTTP_400_BAD_REQUEST)

        for f in files:
            error = validate_uploaded_file(f, allowed_extensions=['jpg', 'jpeg', 'png', 'webp'], max_size_mb=8)
            if error:
                return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

        current_count = maison.photos.count()
        photos_created = []
        for i, f in enumerate(files):
            photo = PhotoMaison.objects.create(
                maison=maison,
                image=f,
                legende=request.data.get('legende', ''),
                ordre=current_count + i,
            )
            photos_created.append(photo)

        return Response(
            PhotoSerializer(photos_created, many=True, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class OwnerMaisonPhotoDeleteView(APIView):
    """Supprimer une photo."""
    permission_classes = [IsVerifiedOwner]

    def delete(self, request, maison_id, photo_id):
        try:
            maison = Maison.objects.get(id=maison_id, proprietaire=request.user)
        except Maison.DoesNotExist:
            return Response({'error': 'Maison introuvable.'}, status=404)

        try:
            photo = maison.photos.get(id=photo_id)
        except PhotoMaison.DoesNotExist:
            return Response({'error': 'Photo introuvable.'}, status=404)

        photo.image.delete(save=False)
        photo.hard_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OwnerNotificationsListView(APIView):
    """Lister les notifications in-app du propriétaire/agence connecté."""
    permission_classes = [IsVerifiedOwner]

    def get(self, request):
        notifications = OwnerNotification.objects.filter(user=request.user)
        data = []
        for notif in notifications:
            data.append({
                'id': str(notif.id),
                'type': notif.type,
                'title': notif.title,
                'message': notif.message,
                'reason': notif.reason,
                'is_read': notif.is_read,
                'read_at': notif.read_at.isoformat() if notif.read_at else None,
                'created_at': notif.created_at.isoformat(),
                'maison': {
                    'id': str(notif.maison.id),
                    'titre': notif.maison.titre,
                } if notif.maison else None,
            })
        return Response(data)


class OwnerNotificationReadView(APIView):
    """Marquer une notification comme lue."""
    permission_classes = [IsVerifiedOwner]

    def post(self, request, notification_id):
        try:
            notif = OwnerNotification.objects.get(id=notification_id, user=request.user)
        except OwnerNotification.DoesNotExist:
            return Response({'error': 'Notification introuvable.'}, status=404)

        if not notif.is_read:
            notif.is_read = True
            notif.read_at = timezone.now()
            notif.save(update_fields=['is_read', 'read_at', 'updated_at'])

        return Response({
            'id': str(notif.id),
            'is_read': notif.is_read,
            'read_at': notif.read_at.isoformat() if notif.read_at else None,
        })
