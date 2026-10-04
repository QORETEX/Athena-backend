"""Stage-by-stage timing test for /api/chat/audio and /ws/voice.

Five phrases:
  1. "Remind me to call mum tomorrow at seven am"     ← reminder, AM/PM check
  2. "What is my battery level?"                       ← get_device_context
  3. "What's the weather like today?"                  ← weather skill
  4. "Set a reminder for my meeting at three pm"       ← second reminder
  5. "Hello, what time is it right now?"               ← simple query, no tool

Run: python scripts/timing_test.py --base-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import time
import wave

import httpx
import websockets


PHRASES = [
    "Remind me to call mum tomorrow at seven am",
    "What is my battery level?",
    "What's the weather like today?",
    "Set a reminder for my meeting at three pm",
    "Hello, what time is it right now?",
]


def synthesize_phrase(text: str) -> bytes:
    """Synthesize text to a WAV bytes buffer using Piper."""
    from app.websocket.voice import _synthesize_speech
    raw = _synthesize_speech(text)
    # raw is raw PCM; wrap in WAV container so /api/chat/audio accepts it
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(raw)
    buf.seek(0)
    return buf.read()


def register_and_login(base: str) -> str:
    """Register a fresh user and return an access token."""
    import random, string
    suffix = "".join(random.choices(string.ascii_lowercase, k=6))
    email = f"timing_{suffix}@test.local"
    with httpx.Client(base_url=base, timeout=30) as c:
        r = c.post("/api/auth/register", json={
            "email": email,
            "password": "testpass123",
            "name": "Timing Tester",
        })
        r.raise_for_status()
        return r.json()["access_token"]


def push_device_context(base: str, token: str) -> None:
    """POST a fake device context so get_device_context has data."""
    ctx = {
        "timestamp": "2026-09-30T10:00:00Z",
        "device": {
            "battery_level": 0.42,
            "is_charging": False,
            "network_type": "wifi",
            "is_screen_on": True,
        },
    }
    with httpx.Client(base_url=base, timeout=10) as c:
        r = c.post(
            "/api/context/update",
            json=ctx,
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()


def run_audio_turn(base: str, token: str, wav: bytes) -> dict:
    """Send one audio turn to /api/chat/audio. Returns timing + result."""
    t0 = time.perf_counter()
    with httpx.Client(base_url=base, timeout=120) as c:
        r = c.post(
            "/api/chat/audio",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": ("phrase.wav", wav, "audio/wav")},
            data={"tts": "false"},
        )
        t_total = time.perf_counter() - t0
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}: {r.text[:200]}", "total_s": t_total}
        d = r.json()
        return {
            "transcript": d.get("transcript", ""),
            "reply": d.get("reply", ""),
            "tool_calls": d.get("tool_calls", []),
            "tool_results": d.get("tool_results", []),
            "error": d.get("error"),
            "total_s": round(t_total, 2),
        }


async def run_ws_turn(base: str, token: str, wav: bytes) -> dict:
    """Send one audio turn over /ws/voice. Returns timing + result."""
    ws_url = base.replace("http://", "ws://").replace("https://", "wss://") + "/ws/voice"

    t0 = time.perf_counter()
    t_transcript = None
    t_reply = None

    result = {
        "transcript": "",
        "reply": "",
        "tool_calls": [],
        "tool_results": [],
        "error": None,
        "total_s": None,
    }

    # Extract raw PCM from WAV for streaming
    buf = io.BytesIO(wav)
    with wave.open(buf, "rb") as wf:
        raw_pcm = wf.readframes(wf.getnframes())

    try:
        async with websockets.connect(ws_url, ping_interval=None) as ws:
            # Auth
            await ws.send(json.dumps({"type": "auth", "token": token}))

            # Send audio in one chunk
            await ws.send(json.dumps({"type": "audio_start", "payload": {}}))
            chunk_size = 4096
            for i in range(0, len(raw_pcm), chunk_size):
                await ws.send(raw_pcm[i:i + chunk_size])
            await ws.send(json.dumps({"type": "audio_end", "payload": {}}))

            # Collect until idle or error
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
                msg = json.loads(raw)
                mtype = msg.get("type", "")
                payload = msg.get("payload", {})

                if mtype == "final_transcript":
                    t_transcript = time.perf_counter() - t0
                    result["transcript"] = payload.get("text", "")
                elif mtype == "tool_call":
                    result["tool_calls"].append(payload)
                elif mtype == "tool_result":
                    result["tool_results"].append(payload)
                elif mtype == "assistant_text":
                    t_reply = time.perf_counter() - t0
                    result["reply"] = payload.get("text", "")
                elif mtype == "status" and payload.get("state") == "idle":
                    break
                elif mtype == "error":
                    result["error"] = payload.get("message") or payload.get("code")
                    break

    except Exception as e:
        result["error"] = str(e)

    t_total = time.perf_counter() - t0
    result["total_s"] = round(t_total, 2)
    result["t_transcript_s"] = round(t_transcript, 2) if t_transcript else None
    result["t_reply_s"] = round(t_reply, 2) if t_reply else None
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    print(f"Base URL: {base}")
    print("Synthesizing audio for 5 phrases (Piper)...")

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    os.chdir(os.path.dirname(os.path.dirname(__file__)))

    t_synth_start = time.perf_counter()
    wavs = []
    for phrase in PHRASES:
        t0 = time.perf_counter()
        wav = synthesize_phrase(phrase)
        elapsed = time.perf_counter() - t0
        print(f"  [{elapsed:.1f}s] {phrase!r}  ({len(wav)} bytes)")
        wavs.append(wav)
    print(f"Total synthesis: {time.perf_counter() - t_synth_start:.1f}s\n")

    print("Registering user and pushing device context...")
    token = register_and_login(base)
    push_device_context(base, token)
    print("Done.\n")

    # ── HTTP /api/chat/audio ────────────────────────────────────────────────
    print("=" * 70)
    print("PATH: /api/chat/audio")
    print("=" * 70)
    for i, (phrase, wav) in enumerate(zip(PHRASES, wavs), 1):
        print(f"\nPhrase {i}: {phrase!r}")
        r = run_audio_turn(base, token, wav)
        if r.get("error") and not r.get("transcript"):
            print(f"  ERROR: {r['error']}")
        else:
            print(f"  Transcript : {r.get('transcript', '')!r}")
            print(f"  Reply      : {r.get('reply', '')!r}")
            tc = r.get("tool_calls", [])
            if tc:
                print(f"  Tool calls : {[t.get('function', {}).get('name','?') if isinstance(t, dict) and 'function' in t else t for t in tc]}")
            tr = r.get("tool_results", [])
            if tr:
                print(f"  Tool results: {tr}")
            if r.get("error"):
                print(f"  Error      : {r['error']}")
            print(f"  Total time : {r['total_s']}s  {'<= 15s OK' if r['total_s'] <= 15 else '** OVER 15s **'}")

    # ── WebSocket /ws/voice ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PATH: /ws/voice")
    print("=" * 70)
    for i, (phrase, wav) in enumerate(zip(PHRASES, wavs), 1):
        print(f"\nPhrase {i}: {phrase!r}")
        r = asyncio.run(run_ws_turn(base, token, wav))
        print(f"  Transcript : {r.get('transcript', '')!r}  (at {r.get('t_transcript_s')}s)")
        print(f"  Reply      : {r.get('reply', '')!r}  (at {r.get('t_reply_s')}s)")
        tc = r.get("tool_calls", [])
        if tc:
            print(f"  Tool calls : {[t.get('tool', '?') for t in tc]}")
        tr = r.get("tool_results", [])
        if tr:
            print(f"  Tool results: {tr}")
        if r.get("error"):
            print(f"  Error      : {r['error']}")
        t_end = r.get("t_reply_s") or r["total_s"]
        print(f"  Turn time  : {t_end}s  {'<= 15s OK' if t_end <= 15 else '** OVER 15s **'}")


if __name__ == "__main__":
    main()
