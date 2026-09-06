from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.skills.weather import handle_weather

router = APIRouter(prefix="/api/weather", tags=["weather"])


class WeatherQuery(BaseModel):
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@router.get("/")
async def get_weather(
    location: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
):
    """Get current weather and 3-day forecast. Provide a city name or coordinates."""
    return await handle_weather(
        location=location, latitude=latitude, longitude=longitude
    )


@router.post("/")
async def post_weather(body: WeatherQuery):
    """Get weather via POST body."""
    return await handle_weather(
        location=body.location, latitude=body.latitude, longitude=body.longitude
    )
