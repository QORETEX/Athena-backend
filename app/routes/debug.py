"""IP debugging route — registered only when DEBUG_CLIENT_IP=true.

Usage: deploy with DEBUG_CLIENT_IP=true, hit /api/_debug/client-ip from two
different networks, confirm get_client_ip returns each network's real public IP,
then set DEBUG_CLIENT_IP=false.  If the real IP appears in cf-connecting-ip or
true-client-ip rather than the rightmost XFF entry, change get_client_ip to
prefer that header.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.rate_limit import get_client_ip
from app.websocket.voice import _ws_connections_per_ip

router = APIRouter()


@router.get("/api/_debug/client-ip")
async def debug_client_ip_route(request: Request):
    return {
        "x_forwarded_for": request.headers.get("x-forwarded-for"),
        "cf_connecting_ip": request.headers.get("cf-connecting-ip"),
        "true_client_ip": request.headers.get("true-client-ip"),
        "request_client_host": request.client.host if request.client else None,
        "get_client_ip": get_client_ip(request),
        "ws_connections_per_ip": dict(_ws_connections_per_ip),
    }
