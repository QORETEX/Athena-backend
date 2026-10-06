#!/bin/bash

echo "════════════════════════════════════════════════════════"
echo "TESTING FIRST REQUEST AFTER SERVER RESTART"
echo "════════════════════════════════════════════════════════"
echo ""
echo "⚠️  Make sure you RESTARTED the server to pick up the retry logic!"
echo ""
echo "Testing first request (this used to fail)..."
echo "────────────────────────────────────────────────────────"

curl -X POST http://localhost:8000/api/chat/text \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello Athena, who created you?","history":[],"tts":false}' \
  2>/dev/null | jq -r '
    if .error then
      "❌ FAILED: " + .error
    else
      "✅ SUCCESS: " + .reply
    end
  '

echo ""
echo "════════════════════════════════════════════════════════"
