"""Detailed Groq API test"""
import asyncio
import httpx
import json

async def test_groq_detailed():
    api_key = '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'
    model = 'openai/gpt-oss-120b'
    
    print("Testing Groq API...")
    print(f"Model: {model}")
    print()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': model,
                    'messages': [{'role': 'user', 'content': 'Say hello in 3 words'}],
                    'max_tokens': 100,
                    'temperature': 0.7,
                },
            )
            
            print(f"Status Code: {response.status_code}")
            print(f"Headers: {dict(response.headers)}")
            print()
            
            if response.status_code == 200:
                data = response.json()
                print("Full Response:")
                print(json.dumps(data, indent=2))
                print()
                
                if 'choices' in data and len(data['choices']) > 0:
                    content = data['choices'][0]['message']['content']
                    print(f"✅ Success! Response: {content}")
                else:
                    print("❌ No choices in response")
            else:
                print(f"❌ Error: {response.text}")
                
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_groq_detailed())
