"""Location matching and distance helpers for sourced insurer branches/advisers."""

from math import asin, cos, radians, sin, sqrt


def find_locations(records, location):
    query = (location or "").strip().lower()
    exact = [
        record for record in records
        if query and query in {
            str(record.get("area", "")).lower(),
            str(record.get("city", "")).lower(),
            str(record.get("pin", "")).lower(),
            str(record.get("postal_code", "")).lower(),
        }
    ]
    if exact:
        return exact, False
    return [], False


def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two coordinate pairs."""
    earth_radius_km = 6371.0
    d_lat, d_lon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(a))


def nearby_locations(records, lat, lon, radius_km):
    """Return records within a radius, with calculated straight-line distances."""
    nearby = []
    for record in records:
        if "lat" not in record or "lon" not in record:
            continue
        item = dict(record)
        item["distance_km"] = round(distance_km(lat, lon, record["lat"], record["lon"]), 1)
        if item["distance_km"] <= radius_km:
            nearby.append(item)
    return sorted(nearby, key=lambda item: item["distance_km"])


def location_centroid(records, location):
    """Approximate a PIN/city centre from the available records."""
    matches, _ = find_locations(records, location)
    coords = [(r["lat"], r["lon"]) for r in matches if "lat" in r and "lon" in r]
    if not coords:
        return None
    return sum(point[0] for point in coords) / len(coords), sum(point[1] for point in coords) / len(coords)
