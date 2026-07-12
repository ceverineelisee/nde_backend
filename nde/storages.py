"""Backends de stockage Cloudinary : public (photos) vs privé (documents KYC sensibles)."""

import os

import cloudinary
import cloudinary.utils
from cloudinary_storage.storage import RawMediaCloudinaryStorage


class PrivateRawMediaCloudinaryStorage(RawMediaCloudinaryStorage):
    """
    Documents sensibles (pièces d'identité, titres de propriété, KBIS) : upload avec le type de
    delivery Cloudinary 'authenticated' (nécessite une URL signée pour être lu), contrairement
    au type 'upload' par défaut de RawMediaCloudinaryStorage qui est accessible à quiconque
    connaît l'URL. Ne fournit pas d'expiration automatique (nécessiterait l'authentification
    par jeton Cloudinary, à activer séparément côté compte) mais empêche toute lecture directe
    non signée.
    """

    def _upload(self, name, content):
        options = {
            'use_filename': True,
            'resource_type': self._get_resource_type(name),
            'tags': self.TAG,
            'type': 'authenticated',
        }
        folder = os.path.dirname(name)
        if folder:
            options['folder'] = folder
        return cloudinary.uploader.upload(content, **options)

    def _get_url(self, name):
        name = self._prepend_prefix(name)
        url, _options = cloudinary.utils.cloudinary_url(
            name,
            resource_type=self._get_resource_type(name),
            type='authenticated',
            sign_url=True,
        )
        return url

    def delete(self, name):
        response = cloudinary.uploader.destroy(
            name,
            invalidate=True,
            resource_type=self._get_resource_type(name),
            type='authenticated',
        )
        return response['result'] == 'ok'
