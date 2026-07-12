import urllib.request
import urllib.parse
import json


def geocode_address(adresse: str, ville: str, code_postal: str = '') -> tuple[float, float] | None:
    """
    Géocode une adresse via l'API Nominatim (OpenStreetMap).
    Retourne (latitude, longitude) ou None si échec.
    """
    query = f"{adresse}, {ville}"
    if code_postal:
        query += f" {code_postal}"

    params = urllib.parse.urlencode({
        'q': query,
        'format': 'json',
        'limit': 1,
        'countrycodes': 'cm',
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
