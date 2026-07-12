"""
Validation des fichiers uploadés hors serializer (vues qui créent les objets directement via
.objects.create() à partir de request.FILES — Django n'exécute les validators de champ que
lors de full_clean()/serializer.is_valid(), jamais lors d'un .save() direct).
"""


def validate_uploaded_file(file, allowed_extensions, max_size_mb=10):
    """Retourne un message d'erreur (str) si le fichier est invalide, sinon None."""
    ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''
    if ext not in allowed_extensions:
        return (
            f"Extension non autorisée : .{ext}. "
            f"Formats acceptés : {', '.join(allowed_extensions)}."
        )
    if file.size > max_size_mb * 1024 * 1024:
        return f"Fichier trop volumineux (max {max_size_mb} MB)."
    return None
