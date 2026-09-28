"""List available Groq models"""
import asyncio
import httpx
import json

async def list_models():
    api_key = '<REDACTED — set GROQ_API_KEY in env>'
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                'https://api.groq.com/openai/v1/models',
                headers={'Authorization': f'Bearer {api_key}'},
            )
            
            if response.status_code == 200:
                data = response.json()
                print("Available Groq models:\n")
                for model in data.get('data', []):
                    print(f"  - {model['id']}")
                return data
            else:
                print(f"Error: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(list_models())
