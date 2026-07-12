#!/bin/bash
set -e

echo "Attente de la base de données PostgreSQL..."
while ! pg_isready -h ${POSTGRES_HOST:-db} -p ${POSTGRES_PORT:-5432} -U ${POSTGRES_USER:-postgres}; do
  sleep 1
done

echo "PostgreSQL est prêt!"

# RUN_MIGRATIONS=false pour les services qui partagent la même base (ex: nde-worker) :
# une seule source de migration évite la course "CREATE TABLE" concurrente au démarrage.
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "Application des migrations de la base de données..."
  python manage.py migrate --noinput
else
  echo "RUN_MIGRATIONS=false : migrations ignorées par ce service."
fi

# echo "Verification/Creation du superutilisateur par defaut..."
# python manage.py create_default_admin

echo "Démarrage de l'application..."
exec "$@"
