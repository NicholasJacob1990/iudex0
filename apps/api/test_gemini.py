import sys
print("Testing Gemini...", flush=True)
from google import genai
print("genai imported", flush=True)
api_key = 'AIzaSyCVHu0BwFrYbt1vhXNJXf4V4iMmL5pe0Uo'
client = genai.Client(api_key=api_key)
print("Client created", flush=True)
try:
    response = client.models.generate_content(model='gemini-2.0-flash', contents='Diga apenas: OK funcionando')
    print('SUCCESS:', response.text, flush=True)
except Exception as e:
    print('ERROR:', type(e).__name__, str(e)[:500], flush=True)
