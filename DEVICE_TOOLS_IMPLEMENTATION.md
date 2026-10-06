# Device Tools Implementation

## Overview
Implemented client-executed device tools that allow the LLM to request actions on the mobile device (calls, messages, device settings, etc.). The backend acts as a passthrough - it tells the LLM about these tools and forwards tool calls to the client via SSE.

## What Was Implemented

### 1. Device Tool Definitions (`device-tool-definitions.json`)
Created 34 device tool definitions covering:
- **Contacts**: search_contacts, get_contact_details
- **Calls**: make_call, get_call_history
- **Messages**: send_sms, get_messages, get_unread_messages
- **Apps**: open_app, search_apps, get_installed_apps
- **Alarms/Timers**: set_alarm, set_timer
- **Location/Navigation**: get_location, navigate_to
- **Photos**: take_photo, search_photos, get_recent_photos
- **Device Settings**: set_volume, set_brightness, toggle_wifi, toggle_bluetooth
- **Media**: play_media, pause_media, skip_media, get_media_status
- **Notes**: create_note, search_notes
- **System**: get_battery_status, get_device_info, read_notification

### 2. Device Tools Module (`app/device_tools.py`)
- Loads device tool definitions from JSON
- Registers them as `Skill` objects with `client_executed=True`
- Called during app startup to make tools available to the LLM

### 3. Streaming Chat Endpoint (`POST /api/chat/stream`)
**Request:**
```json
{
  "message": "user message",
  "history": [{"role": "user", "content": "..."}],
  "conversation_id": "optional-session-id"
}
```

**Response:** SSE stream with events:
- `data: {"type": "token", "content": "text chunk"}` - Text response
- `data: {"type": "tool_call", "tool": "tool_name", "args": {...}}` - Device tool to execute
- `data: {"type": "done"}` - Response complete
- `data: {"type": "error", "message": "..."}` - Error occurred

**Behavior:**
- When LLM calls a `client_executed` tool, emits `tool_call` event and waits for client to execute
- Server-side tools (skills with handlers) are executed automatically
- Does NOT execute device tools - just passes them through

### 4. Tool Result Endpoint (`POST /api/chat/tool-result`)
**Request:**
```json
{
  "tool_name": "search_contacts",
  "result": "Mom (Jane Doe) — +1 555-1234",
  "conversation_id": "optional-session-id",
  "history": [...]
}
```

**Response:** SSE stream (same format as `/stream`)

**Behavior:**
- Appends tool result to conversation as `tool` role message
- Calls LLM again with updated conversation
- Streams the continued response
- Can emit more tool_calls if needed

### 5. LLM Tool Support Updates
- Updated `llm_groq.py` to accept and pass `tools` parameter to API
- Updated `llm_claude.py` to pass tools to Groq fallback
- Tools are sent in OpenAI function calling format

## Usage Flow

1. **Client sends message:** `POST /api/chat/stream` with user message
2. **Backend streams response:**
   - If LLM calls device tool → emits `tool_call` event
   - If LLM responds with text → emits `token` events
3. **Client executes device tool** (e.g., search_contacts)
4. **Client sends result:** `POST /api/chat/tool-result` with result
5. **Backend continues conversation** and streams the LLM's next response

## Example Flow

```bash
# 1. User asks to call Mom
curl -N http://localhost:8000/api/chat/stream \
  -d '{"message": "Call Mom"}'

# Response:
# data: {"type":"tool_call","tool":"search_contacts","args":{"query":"Mom"}}

# 2. Client executes search_contacts locally, finds Mom
# 3. Client sends result back
curl -N http://localhost:8000/api/chat/tool-result \
  -d '{"tool_name":"search_contacts","result":"Mom: 555-1234","history":[...]}'

# Response:
# data: {"type":"tool_call","tool":"make_call","args":{"phone_number":"555-1234"}}

# 4. Client executes make_call
# 5. Client sends result back
curl -N http://localhost:8000/api/chat/tool-result \
  -d '{"tool_name":"make_call","result":"Call initiated","history":[...]}'

# Response:
# data: {"type":"token","content":"Calling Mom now, sir."}
# data: {"type":"done"}
```

## Testing

Run `./test_device_tools.sh` to test various device tools:
```bash
chmod +x test_device_tools.sh
./test_device_tools.sh
```

## Key Design Decisions

1. **Client-executed flag**: Device tools have `client_executed=True`, backend checks this and emits tool_call instead of executing
2. **SSE streaming**: Real-time response streaming allows immediate feedback and multiple tool calls
3. **Tool passthrough**: Backend doesn't implement device tools - client has full control
4. **Standard format**: Uses OpenAI tool format for compatibility with multiple LLMs

## Files Modified/Created

**Created:**
- `device-tool-definitions.json` - 34 device tool definitions
- `app/device_tools.py` - Device tools loader and registration
- `test_device_tools.sh` - Test script

**Modified:**
- `main.py` - Added device tools loading on startup
- `app/routes/chat.py` - Added streaming endpoints and SSE support
- `app/llm_groq.py` - Added tools parameter support
- `app/llm_claude.py` - Pass tools to Groq fallback

## Next Steps

The /tool-result endpoint continuation needs refinement to handle conversation history with tool_calls properly across different LLM providers (current issue with Groq format compatibility).
