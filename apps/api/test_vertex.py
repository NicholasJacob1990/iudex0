import sys
print("Testing Gemini via Vertex AI...", flush=True)
from google import genai
print("genai imported", flush=True)

# Vertex AI mode
project_id = 'gen-lang-client-0727883752'
region = 'us-east5'
client = genai.Client(vertexai=True, project=project_id, location=region)
print(f"Client created (Vertex AI: {project_id})", flush=True)

try:
    response = client.models.generate_content(model='gemini-2.0-flash', contents='Diga apenas: OK funcionando via Vertex')
    print('SUCCESS:', response.text, flush=True)
except Exception as e:
    print('ERROR:', type(e).__name__, str(e)[:600], flush=True)
