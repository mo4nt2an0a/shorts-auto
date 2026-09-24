import os
import sys
import json
import urllib.request
import base64

API_KEY = os.environ["GEMINI_API_KEY"]

if len(sys.argv) < 2:
    raise RuntimeError("Usage: python scripts/analyze_video.py <video_path>")

VIDEO_PATH = sys.argv[1]

if not os.path.exists(VIDEO_PATH):
    raise FileNotFoundError(VIDEO_PATH)

print(f"Analyzing video: {VIDEO_PATH}")

with open(VIDEO_PATH, "rb") as f:
    video_data = base64.b64encode(f.read()).decode("utf-8")

prompt = """
Analyze this video for an automated YouTube Shorts pipeline.

Find EVERY genuinely useful, interesting, funny, surprising, emotional,
informative, or highly engaging moment that could work as an independent
Short.

Do NOT create arbitrary clips just to increase the number of clips.

A clip should contain enough context to make sense by itself.

For every strong moment provide:
- start time in seconds
- end time in seconds
- why the moment is worth clipping
- a short hook/title

Return ONLY valid JSON.
Do NOT use Markdown.
Do NOT use ```json.
Do NOT add any text before or after the JSON.

Use exactly this format:

{
  "clips": [
    {
      "start": 0.0,
      "end": 30.0,
      "reason": "Why this moment is valuable",
      "hook": "Short hook"
    }
  ]
}
"""

url = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models/gemini-3.5-flash-lite:generateContent?key="
    + API_KEY
)

payload = {
    "contents": [
        {
            "parts": [
                {
                    "text": prompt
                },
                {
                    "inline_data": {
                        "mime_type": "video/mp4",
                        "data": video_data
                    }
                }
            ]
        }
    ]
}

data = json.dumps(payload).encode("utf-8")

request = urllib.request.Request(
    url,
    data=data,
    headers={
        "Content-Type": "application/json"
    },
    method="POST"
)

with urllib.request.urlopen(request) as response:
    result = json.loads(response.read().decode("utf-8"))

text = (
    result["candidates"][0]
    ["content"]["parts"][0]["text"]
    .strip()
)

print("===== GEMINI RESPONSE =====")
print(text)

# Remove Markdown code fences if Gemini adds them anyway.
if text.startswith("```"):
    lines = text.splitlines()

    if lines and lines[0].startswith("```"):
        lines = lines[1:]

    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    text = "\n".join(lines).strip()

try:
    parsed = json.loads(text)

except json.JSONDecodeError as e:
    print("===== RAW RESPONSE =====")
    print(text)
    raise RuntimeError(
        f"Gemini did not return valid JSON: {e}"
    )

if "clips" not in parsed:
    raise RuntimeError(
        "Gemini JSON does not contain a 'clips' field"
    )

if not isinstance(parsed["clips"], list):
    raise RuntimeError(
        "'clips' must be a list"
    )

with open(
    "clips.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        parsed,
        f,
        indent=2,
        ensure_ascii=False
    )

print("===== VIDEO ANALYSIS COMPLETE =====")
print(f"Clips found: {len(parsed['clips'])}")
print("Saved to clips.json")
