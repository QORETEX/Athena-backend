"""Quick test for Claude API"""
import asyncio
from app.config import get_settings
from anthropic import AsyncAnthropic

async def test_claude():
    settings = get_settings()

    print(f"API Key loaded: {'Yes' if settings.anthropic_api_key else 'No'}")
    print(f"Key starts with: {settings.anthropic_api_key[:30]}..." if settings.anthropic_api_key else "No key")
    print(f"Model: {settings.claude_model}")

    if not settings.anthropic_api_key:
        print("\n❌ No API key found!")
        return

    print("\nTesting Claude API call...")
    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=100,
            messages=[{"role": "user", "content": "Say hello in 5 words"}]
        )
        print(f"✅ Claude API working!")
        print(f"Response: {response.content[0].text}")
    except Exception as e:
        print(f"❌ Claude API failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_claude())
