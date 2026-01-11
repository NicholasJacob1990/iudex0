#!/usr/bin/env python3
"""
Minimal test to reproduce the AttributeError in Gemini API call
"""
import os
import sys

# Add project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from google import genai
from google.genai import types

# Credentials - use same as mlx_vomo.py
CREDENTIALS_PATH = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/gen-lang-client-0727883752-0bfab2f33e08.json"
if os.path.exists(CREDENTIALS_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_PATH

project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0727883752")

print("Connecting to Vertex AI...")
client = genai.Client(vertexai=True, project=project_id, location="global")

print("Making test request...")
try:
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents="Say hello in Portuguese",
        config=types.GenerateContentConfig(
            max_output_tokens=100,
            temperature=0.1,
            thinking_config=types.ThinkingConfig(
                include_thoughts=False,
                thinking_level="LOW"
            )
        )
    )
    
    print(f"Response type: {type(response)}")
    print(f"Response dir: {[a for a in dir(response) if not a.startswith('_')]}")
    
    # Try accessing .text
    try:
        text = response.text
        print(f"response.text = {text[:100]}...")
    except Exception as e:
        print(f"ERROR accessing .text: {type(e).__name__}: {e}")
    
    # Try accessing candidates
    try:
        if hasattr(response, 'candidates'):
            print(f"Has candidates: {len(response.candidates)}")
            if response.candidates:
                c = response.candidates[0]
                print(f"Candidate content: {c.content}")
    except Exception as e:
        print(f"ERROR accessing candidates: {type(e).__name__}: {e}")

except Exception as e:
    import traceback
    print(f"FULL ERROR: {type(e).__name__}: {e}")
    traceback.print_exc()
