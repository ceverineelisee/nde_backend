import urllib.request
import urllib.parse
import json

from django.conf import settings


def geocode_address(adresse: str, ville: str, code_postal: str = '') -> tuple[float, float] | None:
    """
    Géocode une adresse. Utilise LocationIQ si LOCATIONIQ_API_KEY est configurée (quota
    bien plus confortable que Nominatim en accès direct), sinon retombe sur Nominatim/OSM
    (adapté au développement local, non prévu pour un usage commercial à volume élevé).
    Retourne (latitude, longitude) ou None si échec.
    """
    query = f"{adresse}, {ville}"
    if code_postal:
        query += f" {code_postal}"

    api_key = getattr(settings, 'LOCATIONIQ_API_KEY', '')
    if api_key:
        params = urllib.parse.urlencode({
            'key': api_key,
            'q': query,
            'format': 'json',
            'limit': 1,
            'countrycodes': 'ga',
        })
        url = f"https://us1.locationiq.com/v1/search?{params}"
    else:
        params = urllib.parse.urlencode({
            'q': query,
            'format': 'json',
            'limit': 1,
            'countrycodes': 'ga',
        })
        url = f"https://nominatim.openstreetmap.org/search?{params}"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'NDE-Location-App/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
    except Exception as e:
        print(f"Geocoding error: {e}")

    return None
