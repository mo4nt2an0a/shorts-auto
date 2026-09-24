import os
import json
import urllib.request

key = os.environ["GEMINI_API_KEY"]

url = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models/gemini-3.5-flash-lite:generateContent?key="
    + key
)

payload = {
    "contents": [
        {
            "parts": [
                {
                    "text": "Reply with exactly: GEMINI_OK"
                }
            ]
        }
    ]
}

data = json.dumps(payload).encode("utf-8")

request = urllib.request.Request(
    url,
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST"
)

with urllib.request.urlopen(request) as response:
    result = json.loads(response.read().decode())

text = result["candidates"][0]["content"]["parts"][0]["text"].strip()

print(text)

if text != "GEMINI_OK":
    raise RuntimeError(f"Unexpected response: {text}")
