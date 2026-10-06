#!/bin/bash
# Test script for device tools integration

BASE_URL="http://127.0.0.1:8000/api/chat"

echo "=== Testing Device Tools Integration ==="
echo ""

echo "1. Testing streaming chat with device tool call..."
curl -s -m 5 "$BASE_URL/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Call Mom",
    "history": []
  }' | head -5

echo ""
echo "2. Testing another device tool - battery status..."
curl -s -m 5 "$BASE_URL/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is my battery level?",
    "history": []
  }' | head -5

echo ""
echo "3. Testing search contacts..."
curl -s -m 5 "$BASE_URL/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Find John in my contacts",
    "history": []
  }' | head -5

echo ""
echo "4. Testing send message..."
curl -s -m 5 "$BASE_URL/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Send a text to John saying I will be there soon",
    "history": []
  }' | head -5

echo ""
echo "=== Test Complete ==="
