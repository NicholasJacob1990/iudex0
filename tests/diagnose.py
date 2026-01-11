import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
print(f"🔑 Chave carregada: {api_key[:10]}...{api_key[-5:]}")

# 1. Teste de Autenticação (Raw HTTP)
print("\n📡 Testando /auth/key...")
try:
    resp = requests.get(
        "https://openrouter.ai/api/v1/auth/key",
        headers={"Authorization": f"Bearer {api_key}"}
    )
    print(f"Status: {resp.status_code}")
    print(f"Body: {resp.text}")
except Exception as e:
    print(f"Erro: {e}")

# 2. Teste de Modelos Disponíveis
print("\n📋 Listando modelos (teste de permissão)...")
try:
    resp = requests.get(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {api_key}"}
    )
    if resp.status_code == 200:
        models = resp.json()['data']
        gemini = [m['id'] for m in models if 'gemini' in m['id']]
        print(f"✅ Sucesso! {len(models)} modelos disponíveis.")
        print(f"Gemini models encontrados: {gemini[:5]}...")
    else:
        print(f"❌ Falha: {resp.status_code} - {resp.text}")
except Exception as e:
    print(f"Erro: {e}")

# 3. Teste de Chat (Raw HTTP)
print("\n💬 Testando Chat Completion (Raw)...")
try:
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://localhost:3000",
            "X-Title": "Test Script",
            "Content-Type": "application/json"
        },
        data=json.dumps({
            "model": "google/gemini-2.5-flash",
            "messages": [{"role": "user", "content": "Oi"}],
            "max_tokens": 5
        })
    )
    print(f"Status: {resp.status_code}")
    print(f"Body: {resp.text}")
except Exception as e:
    print(f"Erro: {e}")
