import json
import sys
import urllib.request

# HTTPS endpoint. The old free tier at http://ip-api.com is plaintext-only
# (HTTPS requires a paid key), so a network attacker could spoof the response
# and move the delivery location. ipapi.co serves the same lat/lon over HTTPS
# with no key. On any failure the caller falls back to a hard-coded location.
_GEO_URL = "https://ipapi.co/json/"


def get_current_location():
    """
    Fetches the current location (latitude, longitude) from the IP over HTTPS.
    Returns a dictionary with 'latitude' and 'longitude' keys, or None if failed.
    """
    try:
        # Use a timeout of 3 seconds to avoid hanging. A User-Agent is required;
        # ipapi.co rejects the default urllib agent.
        req = urllib.request.Request(_GEO_URL, headers={"User-Agent": "blinkit-mcp"})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
        if data.get("error"):
            return None
        # ipapi.co uses latitude/longitude; tolerate lat/lon as a fallback.
        lat = data.get("latitude", data.get("lat"))
        lon = data.get("longitude", data.get("lon"))
        if lat is not None and lon is not None:
            return {"latitude": lat, "longitude": lon}
    except Exception as e:
        print(f"Error fetching location from IP API: {e}", file=sys.stderr)
    return None
