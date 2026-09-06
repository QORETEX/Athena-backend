"""Test new Groq models"""
import asyncio
import httpx

async def test_model(model):
    api_key = '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'
    
    print(f"\nTesting: {model}")
    print("-" * 60)
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': model,
                    'messages': [
                        {'role': 'system', 'content': 'You are Athena, created by Qoretex. Be brief.'},
                        {'role': 'user', 'content': 'Who created you?'}
                    ],
                    'max_tokens': 150,
                },
            )
            
            if response.status_code == 200:
                data = response.json()
                msg = data['choices'][0]['message']
                content = msg.get('content') or msg.get('reasoning', '')
                
                print(f"✅ Works! Response:\n{content}\n")
                return True
            else:
                error = response.json().get('error', {}).get('message', response.text)
                print(f"❌ Error: {error[:100]}\n")
                return False
    except Exception as e:
        print(f"❌ Exception: {str(e)[:100]}\n")
        return False

async def main():
    print("=" * 60)
    print("TESTING CURRENT GROQ MODELS")
    print("=" * 60)
    
    models_to_test = [
        'openai/gpt-oss-20b',
        'groq/compound',
        'qwen/qwen3.6-27b',
    ]
    
    working = []
    for model in models_to_test:
        if await test_model(model):
            working.append(model)
    
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if working:
        print(f"✅ Working models: {', '.join(working)}")
        print(f"\n💡 Recommended: {working[0]}")
    else:
        print("❌ No working models found")
    
if __name__ == "__main__":
    asyncio.run(main())
