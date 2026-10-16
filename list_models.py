import os

from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("Models your key can use for generating text:\n")
for m in client.models.list():
    actions = m.supported_actions or []
    if "generateContent" in actions:
        print(m.name.replace("models/", ""))