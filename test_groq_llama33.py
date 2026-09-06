"""Test Groq with llama-3.3-70b-versatile model"""
import asyncio
import httpx
import json

async def test_groq():
    api_key = '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'
    model = 'llama-3.3-70b-versatile'
    
    print(f"Testing Groq with model: {model}\n")
    
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
                    'messages': [
                        {'role': 'system', 'content': 'You are Athena, created by Qoretex. Address user as Sir. Keep responses short.'},
                        {'role': 'user', 'content': 'Hello, who created you?'}
                    ],
                    'max_tokens': 100,
                    'temperature': 0.7,
                },
            )
            
            print(f"Status: {response.status_code}\n")
            
            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                print(f"✅ Success!\n\nResponse:\n{content}\n")
            else:
                print(f"❌ Error: {response.text}")
                
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_groq())
