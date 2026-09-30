import json
import os
import sys
import time
import requests


# ============================================================
# CONFIG
# ============================================================

MODEL = "nvidia/nemotron-3-nano-30b-a3b-omni:free"

MIN_DURATION = 30
MAX_DURATION = 60
MAX_CLIPS = 20

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
UGUU_URL = "https://uguu.se/upload"

VIDEO_PATH = sys.argv[1] if len(sys.argv) > 1 else "input/MASTER.mp4"
OUTPUT_PATH = "clips_nvidia.json"


# ============================================================
# HELPERS
# ============================================================

def fail(message):
    print("")
    print("=" * 60)
    print("ERROR")
    print("=" * 60)
    print(message)
    print("=" * 60)
    sys.exit(1)


def upload_video(video_path):
    print("")
    print("Uploading video to temporary public URL...")

    try:
        with open(video_path, "rb") as f:
            response = requests.post(
                UGUU_URL,
                files={
                    "files[]": (
                        os.path.basename(video_path),
                        f,
                        "video/mp4"
                    )
                },
                timeout=300
            )
    except Exception as e:
        fail(f"Video upload failed: {e}")

    if response.status_code != 200:
        fail(
            f"Temporary upload failed.\n"
            f"HTTP status: {response.status_code}\n"
            f"Response: {response.text[:2000]}"
        )

    try:
        data = response.json()
    except Exception:
        fail(
            "Temporary upload returned invalid JSON:\n"
            + response.text[:2000]
        )

    files = data.get("files", [])

    if not files:
        fail(f"Temporary upload returned no file URL:\n{data}")

    url = files[0]

    print("Temporary video URL created.")

    return url


def extract_json(text):
    text = text.strip()

    # Remove markdown fences if model used them.
    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

        if text.lower().startswith("json"):
            text = text[4:].strip()

    # Direct JSON.
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try extracting first JSON object.
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]

        try:
            return json.loads(candidate)
        except Exception:
            pass

    # Try extracting JSON array.
    start = text.find("[")
    end = text.rfind("]")

    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]

        try:
            return json.loads(candidate)
        except Exception:
            pass

    return None


def timestamp_to_seconds(value):
    if isinstance(value, (int, float)):
        return float(value)

    if not isinstance(value, str):
        return None

    value = value.strip()

    # Plain number.
    try:
        return float(value)
    except Exception:
        pass

    parts = value.split(":")

    try:
        if len(parts) == 2:
            minutes = float(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds

        if len(parts) == 3:
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
    except Exception:
        return None

    return None


def normalize_clips(data):
    if isinstance(data, dict):
        clips = data.get("clips", [])

    elif isinstance(data, list):
        clips = data

    else:
        clips = []

    result = []

    for clip in clips:
        if not isinstance(clip, dict):
            continue

        start = clip.get("start")
        end = clip.get("end")

        if start is None:
            start = clip.get("start_time")

        if end is None:
            end = clip.get("end_time")

        start = timestamp_to_seconds(start)
        end = timestamp_to_seconds(end)

        if start is None or end is None:
            continue

        try:
            start = float(start)
            end = float(end)
        except Exception:
            continue

        duration = end - start

        if duration < MIN_DURATION:
            continue

        if duration > MAX_DURATION:
            continue

        if start < 0:
            continue

        if end <= start:
            continue

        title = (
            clip.get("title")
            or clip.get("hook")
            or clip.get("description")
            or "Untitled clip"
        )

        description = (
            clip.get("description")
            or clip.get("reason")
            or ""
        )

        score = clip.get("score", clip.get("quality_score", 0))

        try:
            score = float(score)
        except Exception:
            score = 0

        result.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(duration, 2),
                "title": str(title).strip(),
                "description": str(description).strip(),
                "score": score,
            }
        )

    return result


def remove_overlaps(clips):
    clips = sorted(
        clips,
        key=lambda x: (
            -x.get("score", 0),
            x["start"]
        )
    )

    selected = []

    for clip in clips:
        overlaps = False

        for existing in selected:
            latest_start = max(
                clip["start"],
                existing["start"]
            )

            earliest_end = min(
                clip["end"],
                existing["end"]
            )

            overlap = max(
                0,
                earliest_end - latest_start
            )

            if overlap > 0:
                overlaps = True
                break

        if not overlaps:
            selected.append(clip)

        if len(selected) >= MAX_CLIPS:
            break

    return sorted(
        selected,
        key=lambda x: x["start"]
    )


# ============================================================
# MAIN
# ============================================================

if not os.path.isfile(VIDEO_PATH):
    fail(f"Video not found: {VIDEO_PATH}")

file_size = os.path.getsize(VIDEO_PATH)

if file_size <= 0:
    fail("Video file is empty.")

print("")
print("=" * 60)
print(" NVIDIA NEMOTRON VIDEO ANALYSIS")
print("=" * 60)
print(f"Video: {VIDEO_PATH}")
print(f"Size: {file_size / 1024 / 1024:.2f} MB")
print(f"Model: {MODEL}")
print("=" * 60)


api_key = os.environ.get("OPENROUTER_API_KEY")

if not api_key:
    fail("OPENROUTER_API_KEY secret is missing.")


# ============================================================
# UPLOAD VIDEO
# ============================================================

video_url = upload_video(VIDEO_PATH)


# ============================================================
# PROMPT
# ============================================================

prompt = f"""
You are an expert short-form video editor.

Analyze the ENTIRE supplied video.

Your task is NOT to divide the video into arbitrary sections.

Find only genuinely strong moments that can work as standalone
YouTube Shorts / Reels / short-form videos.

QUALITY IS MORE IMPORTANT THAN QUANTITY.

Rules:

1. Analyze the whole video before selecting clips.

2. Select ONLY moments that are genuinely interesting, funny,
   surprising, emotional, educational, dramatic, impressive,
   controversial, or otherwise highly engaging.

3. Every selected clip must make sense by itself.

4. The viewer should understand what is happening without needing
   a previous clip.

5. Do NOT select filler.

6. Do NOT select introductions unless the introduction itself is
   highly engaging.

7. Do NOT select outros, dead air, greetings, pauses, loading,
   setup, repeated explanations, or irrelevant conversation.

8. Do NOT create arbitrary 30-60 second windows just to satisfy
   the duration requirement.

9. Do NOT create multiple clips from the same moment.

10. Avoid overlapping clips.

11. If the same event contains several possible moments, select
    only the strongest self-contained version.

12. Prefer natural beginning and ending points.

13. A clip may be shorter than 60 seconds, but it must be at least
    {MIN_DURATION} seconds.

14. Maximum duration is {MAX_DURATION} seconds.

15. If the video contains only 2 genuinely strong moments,
    return 2 clips.

16. If it contains only 1 genuinely strong moment, return 1 clip.

17. If there are no genuinely strong moments, return an empty list.

18. NEVER invent events, dialogue, timestamps, or information.

19. Timestamp accuracy is extremely important.

20. The clip should contain the complete setup and payoff whenever
    necessary.

Return ONLY valid JSON.

Required format:

{{
  "clips": [
    {{
      "start": 123.45,
      "end": 168.20,
      "title": "Short descriptive title",
      "description": "Why this exact moment works as a standalone short",
      "score": 9
    }}
  ]
}}

Score each candidate from 1 to 10 based on short-form potential.

Only return clips with a genuinely strong score.

Remember:
QUALITY > QUANTITY.
Do not manufacture clips.
"""


# ============================================================
# OPENROUTER REQUEST
# ============================================================

print("")
print("=" * 60)
print("SENDING VIDEO TO OPENROUTER")
print("=" * 60)
print(f"Model: {MODEL}")
print("")


headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}


payload = {
    "model": MODEL,
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt,
                },
                {
                    "type": "video_url",
                    "video_url": {
                        "url": video_url
                    },
                },
            ],
        }
    ],
    "temperature": 0.2,
}


try:
    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=payload,
        timeout=1800
    )
except Exception as e:
    fail(f"OpenRouter request failed: {e}")


print(f"OpenRouter HTTP status: {response.status_code}")


if response.status_code != 200:
    print("")
    print("===== OPENROUTER ERROR =====")

    try:
        print(json.dumps(response.json(), indent=2))
    except Exception:
        print(response.text[:5000])

    print("============================")

    fail(
        f"ERROR: OpenRouter returned HTTP {response.status_code}"
    )


# ============================================================
# PARSE RESPONSE
# ============================================================

try:
    response_data = response.json()
except Exception as e:
    fail(f"OpenRouter returned invalid JSON: {e}")


try:
    message = response_data["choices"][0]["message"]
except Exception:
    print(json.dumps(response_data, indent=2))
    fail("Could not find model message in OpenRouter response.")


content = message.get("content", "")

if isinstance(content, list):
    parts = []

    for part in content:
        if isinstance(part, dict):
            if "text" in part:
                parts.append(str(part["text"]))

    content = "\n".join(parts)

content = str(content).strip()


print("")
print("=" * 60)
print("MODEL RESPONSE")
print("=" * 60)
print(content[:10000])
print("=" * 60)


if not content:
    fail("Model returned an empty response.")


data = extract_json(content)

if data is None:
    fail("Could not parse valid JSON from model response.")


# ============================================================
# VALIDATE CLIPS
# ============================================================

clips = normalize_clips(data)

print("")
print(f"Valid clips before overlap filtering: {len(clips)}")

clips = remove_overlaps(clips)

print(f"Valid clips after overlap filtering: {len(clips)}")


# ============================================================
# SAVE RESULT
# ============================================================

output = {
    "model": MODEL,
    "video": VIDEO_PATH,
    "video_size_bytes": file_size,
    "clips": clips,
}


with open(
    OUTPUT_PATH,
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        output,
        f,
        indent=2,
        ensure_ascii=False
    )


print("")
print("=" * 60)
print("NVIDIA ANALYSIS COMPLETE")
print("=" * 60)
print(f"Output: {OUTPUT_PATH}")
print(f"Clips: {len(clips)}")
print("=" * 60)

for index, clip in enumerate(clips, 1):
    print(
        f"{index}. "
        f"{clip['start']:.2f}s → "
        f"{clip['end']:.2f}s "
        f"({clip['duration']:.2f}s) | "
        f"score={clip['score']}"
    )
    print(f"   {clip['title']}")
