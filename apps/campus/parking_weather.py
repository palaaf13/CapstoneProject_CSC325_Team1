"""Cached weather endpoint for the RamHub parking page."""
import json
import logging
from urllib.request import Request, urlopen

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET

LOG = logging.getLogger(__name__)
FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude=40.7524&longitude=-73.4280"
    "&current=temperature_2m,apparent_temperature,weather_code,is_day"
    "&hourly=precipitation_probability&temperature_unit=fahrenheit"
    "&timezone=America%2FNew_York&forecast_days=1"
)
CACHE_KEY = "ramhub:parking:weather:v1"
CACHE_SECONDS = 600


@require_GET
def parking_weather(request):
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return JsonResponse(cached)
    try:
        req = Request(FORECAST_URL, headers={
            "Accept": "application/json", "User-Agent": "RamHub/1.0"
        })
        with urlopen(req, timeout=6) as response:
            payload = json.loads(response.read(256_000).decode("utf-8"))
        current = payload.get("current")
        if (
            not isinstance(current, dict)
            or not isinstance(current.get("temperature_2m"), (int, float))
            or not isinstance(current.get("weather_code"), (int, float))
        ):
            raise ValueError("Invalid forecast response")
        cache.set(CACHE_KEY, payload, CACHE_SECONDS)
        return JsonResponse(payload)
    except Exception:
        LOG.warning("Parking weather unavailable", exc_info=True)
        return JsonResponse({"error": "Weather temporarily unavailable"}, status=503)
