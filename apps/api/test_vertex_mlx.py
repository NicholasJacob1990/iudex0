import sys
import os
print("Testing Gemini via Vertex AI (mlx_vomo config)...", flush=True)

# Usar o arquivo de Service Account do mlx_vomo
CREDENTIALS_PATH = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/gen-lang-client-0727883752-0bfab2f33e08.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_PATH
print(f"Credentials: {CREDENTIALS_PATH}", flush=True)

from google import genai
print("genai imported", flush=True)

# Usar location=global como no mlx_vomo
project_id = 'gen-lang-client-0727883752'
client = genai.Client(vertexai=True, project=project_id, location="global")
print(f"Client created (Vertex AI: {project_id}, location=global)", flush=True)

try:
    response = client.models.generate_content(model='gemini-2.0-flash', contents='Diga apenas: OK funcionando via Vertex')
    print('SUCCESS:', response.text, flush=True)
except Exception as e:
    print('ERROR:', type(e).__name__, str(e)[:600], flush=True)
