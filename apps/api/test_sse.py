import requests
import json
import sseclient

url = "http://localhost:8001/api/transcription/vomo/batch/stream"
files = [('files', ('test_audio.txt', b'dummy content', 'text/plain'))]
data = {
    "mode": "RAW",
    "thinking_level": "low",
    "model_selection": "gemini-3-flash-preview"
}

print(f"Connecting to {url}...")
try:
    response = requests.post(url, files=files, data=data, stream=True)
    print(f"Response status: {response.status_code}")
    
    client = sseclient.SSEClient(response)
    for event in client.events():
        print(f"Event: {event.event}")
        print(f"Data: {event.data}")
        if event.event == 'complete' or event.event == 'error':
            break
            
except Exception as e:
    print(f"Error: {e}")
