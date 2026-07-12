from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser

from nde.models import Maison, Commentaire, PieceJointeCommentaire
from nde.upload_validation import validate_uploaded_file

ALLOWED_COMMENT_ATTACHMENT_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx', 'xls', 'xlsx']


class MaisonCommentairesView(APIView):
    """Liste et création de commentaires sur une maison publiée."""
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_authenticators(self):
        if self.request.method == 'GET':
            return []
        return super().get_authenticators()

    def get(self, request, maison_id):
        try:
            maison = Maison.objects.get(id=maison_id, statut='publiee')
        except Maison.DoesNotExist:
            return Response({'error': 'Maison introuvable.'}, status=404)

        commentaires = (
            Commentaire.objects
            .filter(maison=maison)
            .select_related('auteur')
            .prefetch_related('pieces_jointes')
            .order_by('-created_at')
        )

        data = []
        for c in commentaires:
            pieces = []
            for pj in c.pieces_jointes.all():
                pieces.append({
                    'id': str(pj.id),
                    'nom_fichier': pj.nom_fichier,
                    'url': request.build_absolute_uri(pj.fichier.url) if pj.fichier else None,
                })

            data.append({
                'id': str(c.id),
                'contenu': c.contenu,
                'created_at': c.created_at.isoformat(),
                'auteur': {
                    'id': str(c.auteur.id),
                    'name': c.auteur.name,
                    'role': c.auteur.role,
                    'photo_profil': request.build_absolute_uri(c.auteur.photo_profil.url) if c.auteur.photo_profil else None,
                },
                'pieces_jointes': pieces,
            })

        return Response(data)

    def post(self, request, maison_id):
        try:
            maison = Maison.objects.get(id=maison_id, statut='publiee')
        except Maison.DoesNotExist:
            return Response({'error': 'Maison introuvable.'}, status=404)

        contenu = request.data.get('contenu', '').strip()
        if not contenu:
            return Response(
                {'error': 'Le contenu du commentaire est obligatoire.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fichiers = request.FILES.getlist('fichiers')
        for f in fichiers:
            error = validate_uploaded_file(f, allowed_extensions=ALLOWED_COMMENT_ATTACHMENT_EXTENSIONS, max_size_mb=10)
            if error:
                return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

        commentaire = Commentaire.objects.create(
            maison=maison,
            auteur=request.user,
            contenu=contenu,
        )

        pieces = []
        for f in fichiers:
            pj = PieceJointeCommentaire.objects.create(
                commentaire=commentaire,
                fichier=f,
                nom_fichier=f.name,
            )
            pieces.append({
                'id': str(pj.id),
                'nom_fichier': pj.nom_fichier,
                'url': request.build_absolute_uri(pj.fichier.url),
            })

        return Response({
            'id': str(commentaire.id),
            'contenu': commentaire.contenu,
            'created_at': commentaire.created_at.isoformat(),
            'auteur': {
                'id': str(request.user.id),
                'name': request.user.name,
                'role': request.user.role,
                'photo_profil': request.build_absolute_uri(request.user.photo_profil.url) if request.user.photo_profil else None,
            },
            'pieces_jointes': pieces,
        }, status=status.HTTP_201_CREATED)


class CommentaireDeleteView(APIView):
    """Suppression d'un commentaire par son auteur ou un admin."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, commentaire_id):
        try:
            commentaire = Commentaire.objects.get(id=commentaire_id)
        except Commentaire.DoesNotExist:
            return Response({'error': 'Commentaire introuvable.'}, status=404)

        if commentaire.auteur != request.user and request.user.role != 'admin':
            return Response({'error': 'Non autorisé.'}, status=403)

        commentaire.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
