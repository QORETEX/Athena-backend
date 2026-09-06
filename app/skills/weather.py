from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.skills.base import Skill, register_skill

logger = logging.getLogger(__name__)


async def handle_weather(
    location: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict:
    settings = get_settings()
    location_name = location

    if location and (latitude is None or longitude is None):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": location, "count": 1, "language": "en"},
                )
                results = resp.json().get("results", [])
                if not results:
                    return {"error": f"Location not found: {location}"}
                latitude = results[0]["latitude"]
                longitude = results[0]["longitude"]
                location_name = f"{results[0]['name']}, {results[0].get('country', '')}"
        except httpx.HTTPError as e:
            return {"error": f"Geocoding failed: {e}"}

    lat = latitude or settings.default_latitude
    lon = longitude or settings.default_longitude

    if lat is None or lon is None:
        return {"error": "No location provided and no default configured in .env"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                settings.weather_api_url,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current_weather": True,
                    "forecast_days": 3,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
                    "timezone": "auto",
                },
            )
            data = resp.json()
    except httpx.HTTPError as e:
        return {"error": f"Weather API request failed: {e}"}

    current = data.get("current_weather", {})
    daily = data.get("daily", {})

    forecast = []
    if daily.get("time"):
        for i, date in enumerate(daily["time"]):
            forecast.append({
                "date": date,
                "high": daily.get("temperature_2m_max", [None])[i],
                "low": daily.get("temperature_2m_min", [None])[i],
                "precipitation_mm": daily.get("precipitation_sum", [None])[i],
                "weathercode": daily.get("weathercode", [None])[i],
            })

    return {
        "location": location_name or f"{lat}, {lon}",
        "current": {
            "temperature": current.get("temperature"),
            "windspeed": current.get("windspeed"),
            "winddirection": current.get("winddirection"),
            "weathercode": current.get("weathercode"),
            "is_day": current.get("is_day"),
        },
        "forecast": forecast,
    }


register_skill(
    Skill(
        name="get_weather",
        description="Get current weather and forecast for a location. Can accept a city name, or latitude/longitude coordinates.",
        parameters={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City or place name (e.g., 'Paris', 'New York')",
                },
                "latitude": {
                    "type": "number",
                    "description": "Latitude coordinate (optional if location name given)",
                },
                "longitude": {
                    "type": "number",
                    "description": "Longitude coordinate (optional if location name given)",
                },
            },
        },
        handler=handle_weather,
        timeout=20,
    )
)
