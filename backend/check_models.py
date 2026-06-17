import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
response = requests.get(url).json()
for m in response.get("models", []):
    if "gemini" in m["name"]:
        print(m["name"])
