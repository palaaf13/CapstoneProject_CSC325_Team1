"""Django integration tests for the RamHub parking page."""
import io
import json
from unittest.mock import patch
from urllib.error import URLError

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.campus.parking_weather import CACHE_KEY


class ParkingPageTests(TestCase):
    def test_page_includes_assets_and_navigation(self):
        response = self.client.get(reverse("campus:parking"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "parking/parking.js")
        self.assertContains(response, "parking/parking.css")
        self.assertContains(response, 'id="map3d"')
        self.assertContains(response, 'id="map2d"')
        self.assertContains(response, 'id="destination"')


class ParkingWeatherTests(TestCase):
    def setUp(self):
        cache.delete(CACHE_KEY)

    @patch("apps.campus.parking_weather.urlopen")
    def test_weather_success_is_cached(self, mocked_open):
        payload = {
            "current": {"temperature_2m": 70, "weather_code": 1},
            "hourly": {"time": [], "precipitation_probability": []},
        }
        mocked_open.return_value.__enter__.return_value = io.BytesIO(
            json.dumps(payload).encode("utf-8")
        )
        url = reverse("campus:parking_weather")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(url).json()["current"]["temperature_2m"], 70)
        self.assertEqual(mocked_open.call_count, 1)

    @patch("apps.campus.parking_weather.urlopen", side_effect=URLError("offline"))
    def test_weather_failure_is_safe(self, mocked_open):
        response = self.client.get(reverse("campus:parking_weather"))
        self.assertEqual(response.status_code, 503)
        self.assertIn("error", response.json())
