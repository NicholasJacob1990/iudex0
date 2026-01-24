import requests
import json

try:
    print("Attempting to hit http://localhost:8000/api/auth/login-test")
    response = requests.post("http://localhost:8000/api/auth/login-test")
    print(f"Status Code: {response.status_code}")
    try:
        print("Response JSON:", response.json())
    except:
        print("Response Text:", response.text)
except Exception as e:
    print(f"Error: {e}")
