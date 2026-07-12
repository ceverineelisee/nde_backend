import math

from django.db.models import Q, F
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from nde.contact_access import contact_access_payload, register_contact_reveal
from nde.models import Maison, PhotoMaison


def serialize_photo(photo, request):
    return {
        'id': str(photo.id),
        'url': request.build_absolute_uri(photo.image.url) if photo.image else None,
        'legende': photo.legende,
    }


def serialize_maison_card(maison, request):
    first_photo = maison.photos.first()
    return {
        'id': str(maison.id),
        'titre': maison.titre,
        'description': maison.description[:150] + ('...' if len(maison.description) > 150 else ''),
        'prix_location': str(maison.prix_location),
        'adresse': maison.adresse,
        'ville': maison.ville,
        'code_postal': maison.code_postal,
        'date_publication': maison.date_publication.isoformat() if maison.date_publication else None,
        'photos_count': maison.photos.count(),
        'photo_principale': request.build_absolute_uri(first_photo.image.url) if first_photo and first_photo.image else None,
        'latitude': maison.latitude,
        'longitude': maison.longitude,
        'proprietaire': {
            'name': maison.proprietaire.name,
            'photo_profil': request.build_absolute_uri(maison.proprietaire.photo_profil.url) if maison.proprietaire.photo_profil else None,
        },
    }


def serialize_maison_detail(maison, request):
    photos = [serialize_photo(p, request) for p in maison.photos.all()]
    return {
        'id': str(maison.id),
        'titre': maison.titre,
        'description': maison.description,
        'prix_location': str(maison.prix_location),
        'adresse': maison.adresse,
        'ville': maison.ville,
        'code_postal': maison.code_postal,
        'date_publication': maison.date_publication.isoformat() if maison.date_publication else None,
        'photos': photos,
        'latitude': maison.latitude,
        'longitude': maison.longitude,
        'proprietaire': {
            'id': str(maison.proprietaire.id),
            'name': maison.proprietaire.name,
            'photo_profil': request.build_absolute_uri(maison.proprietaire.photo_profil.url) if maison.proprietaire.photo_profil else None,
            'role': maison.proprietaire.role,
            'phone': maison.proprietaire.phone or None,
            'has_contact_phone': bool(maison.proprietaire.phone),
            'country_code': maison.proprietaire.country_code or '+237',
        },
    }


def serialize_maison_pin(maison, request):
    """Version allégée pour l'affichage d'un pin sur la carte."""
    return {
        'id': str(maison.id),
        'titre': maison.titre,
        'prix_location': str(maison.prix_location),
        'ville': maison.ville,
        'latitude': maison.latitude,
        'longitude': maison.longitude,
        'photos_count': maison.photos.count(),
        'photo_principale': (
            request.build_absolute_uri(maison.photos.first().image.url)
            if maison.photos.first() and maison.photos.first().image else None
        ),
        'proprietaire': {
            'name': maison.proprietaire.name,
            'role': maison.proprietaire.role,
        },
    }


def haversine_km(lat1, lng1, lat2, lng2):
    """Distance en kilomètres entre deux points géographiques."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


class PublicMaisonsCarteView(APIView):
    """
    Maisons publiées géolocalisées, pour affichage sous forme de pins sur une carte.

    Filtrage possible par zone visible de la carte (north/south/east/west) ou par
    position + rayon autour de l'utilisateur connecté (lat/lng/radius_km).
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        qs = Maison.objects.filter(
            statut='publiee',
            latitude__isnull=False,
            longitude__isnull=False,
        ).select_related('proprietaire').prefetch_related('photos')

        ville = request.query_params.get('ville', '')
        if ville:
            qs = qs.filter(ville__icontains=ville)

        north = request.query_params.get('north')
        south = request.query_params.get('south')
        east = request.query_params.get('east')
        west = request.query_params.get('west')
        if north and south and east and west:
            try:
                qs = qs.filter(
                    latitude__lte=float(north),
                    latitude__gte=float(south),
                    longitude__lte=float(east),
                    longitude__gte=float(west),
                )
            except ValueError:
                return Response({'error': 'Paramètres de zone invalides.'}, status=400)

        lat = request.query_params.get('lat')
        lng = request.query_params.get('lng')
        radius_km = request.query_params.get('radius_km')
        if lat and lng and radius_km:
            try:
                lat, lng, radius_km = float(lat), float(lng), float(radius_km)
            except ValueError:
                return Response({'error': 'Paramètres de position invalides.'}, status=400)
            qs = [m for m in qs if haversine_km(lat, lng, m.latitude, m.longitude) <= radius_km]

        data = [serialize_maison_pin(m, request) for m in qs]
        return Response(data)


class PublicMaisonsListView(APIView):
    """Liste des maisons publiées, accessible à tous."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        search = request.query_params.get('search', '')
        ville = request.query_params.get('ville', '')

        qs = Maison.objects.filter(
            statut='publiee'
        ).select_related('proprietaire').prefetch_related('photos').order_by('-date_publication')

        if search:
            qs = qs.filter(
                Q(titre__icontains=search) |
                Q(description__icontains=search) |
                Q(ville__icontains=search) |
                Q(adresse__icontains=search)
            )
        if ville:
            qs = qs.filter(ville__icontains=ville)

        data = [serialize_maison_card(m, request) for m in qs]
        return Response(data)


class PublicMaisonDetailView(APIView):
    """Détail d'une maison publiée, accessible à tous."""
    permission_classes = [AllowAny]
    authentication_classes = [JWTAuthentication]

    def get(self, request, maison_id):
        try:
            maison = Maison.objects.select_related('proprietaire').prefetch_related('photos').get(
                id=maison_id, statut='publiee'
            )
        except Maison.DoesNotExist:
            return Response({'error': 'Maison introuvable.'}, status=404)

        Maison.objects.filter(id=maison_id).update(views_count=F('views_count') + 1)
        maison.views_count += 1

        viewer = (
            request.user if getattr(request.user, 'is_authenticated', False) else None
        )
        payload = serialize_maison_detail(maison, request)
        meta = contact_access_payload(viewer, maison)
        if meta['phone_visible']:
            register_contact_reveal(viewer, maison)
        else:
            payload['proprietaire']['phone'] = None

        payload['contact_access'] = meta
        return Response(payload)


class PublicVillesListView(APIView):
    """Liste des villes avec des maisons publiées."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        villes = (
            Maison.objects.filter(statut='publiee')
            .values_list('ville', flat=True)
            .distinct()
            .order_by('ville')
        )
        data = []
        for v in villes:
            count = Maison.objects.filter(statut='publiee', ville=v).count()
            data.append({'name': v, 'count': count})
        return Response(data)
