
import os
import sys
from google import genai
from google.genai import types
from colorama import Fore, init

init(autoreset=True)

MODEL_ID = "gemini-3-flash-preview"
PROJECT_ID = "gen-lang-client-0727883752"
LOCATION = "us-central1"
CREDENTIALS_PATH = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/gen-lang-client-0727883752-f72a632e4ec2.json"

def test_service_account():
    print(f"\n{Fore.BLUE}🧪 TEST 1: Service Account (Settings Actuals)...")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_PATH
    try:
        client = genai.Client(
            vertexai=True,
            project=PROJECT_ID,
            location=LOCATION
        )
        print(f"Client initialized.")
        response = client.models.count_tokens(model=MODEL_ID, contents="Hello Vertex")
        print(f"{Fore.GREEN}✅ SUCCESS! Tokens: {response}")
    except Exception as e:
        print(f"{Fore.RED}❌ FAILED: {e}")

def test_api_key_vertex():
    print(f"\n{Fore.BLUE}🧪 TEST 2: API Key + Vertex (User Snippet Style)...")
    # Try to find a key
    api_key = os.getenv("GOOGLE_CLOUD_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print(f"{Fore.YELLOW}⚠️ No API Key found in env to test.")
        return

    try:
        # Note: User snippet uses api_key arg in Client without project/location
        client = genai.Client(
            vertexai=True,
            api_key=api_key
        )
        print(f"Client initialized with API Key: {api_key[:5]}... (No project/loc args)")
        response = client.models.count_tokens(model=MODEL_ID, contents="Hello Vertex Key")
        print(f"{Fore.GREEN}✅ SUCCESS! Tokens: {response}")
    except Exception as e:
        print(f"{Fore.RED}❌ FAILED: {e}")
    except Exception as e:
        print(f"{Fore.RED}❌ FAILED: {e}")

def test_ai_studio():
    print(f"\n{Fore.BLUE}🧪 TEST 3: AI Studio (vertexai=False)...")
    api_key = os.getenv("GOOGLE_CLOUD_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    try:
        client = genai.Client(
            vertexai=False,
            api_key=api_key
        )
        print(f"Client initialized for AI Studio.")
        response = client.models.count_tokens(model=MODEL_ID, contents="Hello AI Studio")
        print(f"{Fore.GREEN}✅ SUCCESS! Tokens: {response}")
    except Exception as e:
        print(f"{Fore.RED}❌ FAILED: {e}")

def test_baseline_vertex():
    print(f"\n{Fore.BLUE}🧪 TEST 5: Baseline Vertex (gemini-1.5-flash-002)...")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_PATH
    try:
        client = genai.Client(
            vertexai=True,
            project=PROJECT_ID,
            location=LOCATION
        )
        response = client.models.count_tokens(model="gemini-1.5-flash-002", contents="Hello baseline")
        print(f"{Fore.GREEN}✅ SUCCESS! baseline Tokens: {response}")
    except Exception as e:
        print(f"{Fore.RED}❌ FAILED: {e}")

def list_vertex_models():
    print(f"\n{Fore.BLUE}🧪 TEST 4: Listing ALL Vertex Models...")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_PATH
    try:
        client = genai.Client(
            vertexai=True,
            project=PROJECT_ID,
            location=LOCATION
        )
        print("Models available on Vertex:")
        for model in client.models.list():
            print(f" - {model.name}")
    except Exception as e:
        print(f"{Fore.RED}❌ FAILED: {e}")

def test_exact_names():
    print(f"\n{Fore.BLUE}🧪 TEST 6: Exact Names from List...")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_PATH
    try:
        client = genai.Client(
            vertexai=True,
            project=PROJECT_ID,
            location=LOCATION
        )
        
        models_to_test = [
            "gemini-3-flash-preview",
            "publishers/google/models/gemini-3-flash-preview",
            "gemini-2.5-flash",
            "publishers/google/models/gemini-2.5-flash"
        ]
        
        for m in models_to_test:
            try:
                response = client.models.count_tokens(model=m, contents="ping")
                print(f"{Fore.GREEN}✅ SUCCESS for {m}!")
            except Exception as e:
                print(f"{Fore.RED}❌ FAILED for {m}: {e}")
    except Exception as e:
        print(f"{Fore.RED}❌ FAILED to init: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    import importlib.metadata
    try:
        version = importlib.metadata.version("google-genai")
        print(f"{Fore.MAGENTA}📦 google-genai version: {version}")
    except:
        print(f"{Fore.MAGENTA}📦 google-genai version: complicated")

    load_dotenv("/Users/nicholasjacob/Documents/Aplicativos/Iudex/.env")
    
    # test_service_account() # Skipping known fail
    # test_api_key_vertex()  # Skipping known fail
    # test_ai_studio()       # Known success
    # list_vertex_models()   # Known output
    test_exact_names()
