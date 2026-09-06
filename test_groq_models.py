"""Test different Groq models"""
import asyncio
import httpx

async def test_model(model):
    api_key = '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'
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': model,
                    'messages': [{'role': 'user', 'content': 'Say hello'}],
                    'max_tokens': 50,
                },
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                print(f"✅ {model}: {content[:50]}...")
                return True
            else:
                print(f"❌ {model}: {response.json()['error']['message'][:80]}")
                return False
    except Exception as e:
        print(f"❌ {model}: {str(e)[:80]}")
        return False

async def main():
    print("Testing Groq models...\n")
    
    models = [
        'llama-3.1-70b-versatile',
        'llama-3.1-8b-instant',
        'llama3-70b-8192',
        'mixtral-8x7b-32768',
        'gemma2-9b-it',
    ]
    
    for model in models:
        await test_model(model)
    
if __name__ == "__main__":
    asyncio.run(main())
