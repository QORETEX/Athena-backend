"""Test all LLM providers to see which are working"""
import asyncio
from app.config import get_settings

async def test_all_llms():
    settings = get_settings()

    print("=" * 60)
    print("🤖 LLM CONFIGURATION TEST")
    print("=" * 60)

    # Test Claude
    print("\n1️⃣  CLAUDE (Anthropic)")
    print("-" * 60)
    if settings.anthropic_api_key:
        print(f"✅ API Key configured: {settings.anthropic_api_key[:30]}...")
        print(f"   Model: {settings.claude_model}")
        try:
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            response = await client.messages.create(
                model=settings.claude_model,
                max_tokens=50,
                messages=[{"role": "user", "content": "Say 'Hello from Claude' in 5 words"}]
            )
            print(f"✅ WORKING! Response: {response.content[0].text}")
        except Exception as e:
            print(f"❌ ERROR: {str(e)[:100]}")
    else:
        print("⚠️  No API key configured")

    # Test Groq
    print("\n2️⃣  GROQ (Fast & Free)")
    print("-" * 60)
    if settings.groq_api_key:
        print(f"✅ API Key configured: {settings.groq_api_key[:20]}...")
        print(f"   Model: {settings.groq_model}")
        try:
            from app.llm_groq import get_groq_llm
            groq = get_groq_llm()
            response = await groq.chat([
                {"role": "user", "content": "Say 'Hello from Groq' in 5 words"}
            ], max_tokens=50)
            print(f"✅ WORKING! Response: {response['message']['content']}")
        except Exception as e:
            print(f"❌ ERROR: {str(e)[:100]}")
    else:
        print("⚠️  No API key configured")
        print("   Get free key: https://console.groq.com/")

    # Test NVIDIA
    print("\n3️⃣  NVIDIA NIM (Free)")
    print("-" * 60)
    if settings.nvidia_api_key:
        print(f"✅ API Key configured: {settings.nvidia_api_key[:20]}...")
        print(f"   Model: {settings.nvidia_model}")
        try:
            from app.llm_nvidia import get_nvidia_llm
            nvidia = get_nvidia_llm()
            response = await nvidia.chat([
                {"role": "user", "content": "Say 'Hello from NVIDIA' in 5 words"}
            ], max_tokens=50)
            print(f"✅ WORKING! Response: {response['message']['content']}")
        except Exception as e:
            print(f"❌ ERROR: {str(e)[:100]}")
    else:
        print("⚠️  No API key configured")
        print("   Get free key: https://build.nvidia.com/")

    # Test Ollama
    print("\n4️⃣  OLLAMA (Local)")
    print("-" * 60)
    print(f"   URL: {settings.ollama_base_url}")
    print(f"   Model: {settings.ollama_model}")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            models = response.json().get("models", [])
            if models:
                print(f"✅ Ollama running! Available models: {len(models)}")
                print(f"   Models: {', '.join([m['name'] for m in models[:3]])}")
            else:
                print("⚠️  Ollama running but no models installed")
                print("   Run: ollama pull llama3.2")
    except Exception as e:
        print(f"❌ Ollama not running")
        print(f"   Install: brew install ollama")
        print(f"   Start: ollama serve")

    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)

    working = []
    if settings.anthropic_api_key: working.append("Claude")
    if settings.groq_api_key: working.append("Groq")
    if settings.nvidia_api_key: working.append("NVIDIA")

    if working:
        print(f"✅ Configured: {', '.join(working)}")
        print(f"\n🎯 Priority: Claude → Groq → NVIDIA → Ollama")
        print(f"   Your system will use: {working[0]} (if working)")
    else:
        print("⚠️  No cloud LLMs configured (will use Ollama only)")
        print("\n💡 Recommendation: Setup Groq (FREE, 2 minutes)")
        print("   https://console.groq.com/")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(test_all_llms())
