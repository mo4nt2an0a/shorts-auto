import json
import os
import sys
import time
import requests


# ============================================================
# CONFIG
# ============================================================

MODEL = "qwen/qwen3.8-27b:free"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
UGUU_URL = "https://uguu.se/upload"

VIDEO_PATH = sys.argv[1] if len(sys.argv) > 1 else "input/MASTER.mp4"
OUTPUT_PATH = "clips_qwen.json"

MIN_DURATION = 30
MAX_DURATION = 60
MAX_CLIPS = 20


# ============================================================
# HELPERS
# ============================================================

def upload_video(video_path):
    print("Uploading video to temporary public URL...")

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    size = os.path.getsize(video_path)

    if size == 0:
        raise RuntimeError("Video file is 0 bytes.")

    print(f"Local video size: {size / (1024 * 1024):.2f} MB")

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

    print(f"Upload HTTP status: {response.status_code}")

    response.raise_for_status()

    data = response.json()

    if isinstance(data, dict):
        files = data.get("files")

        if files and isinstance(files, list):
            first = files[0]

            if isinstance(first, dict):
                url = first.get("url")

                if url:
                    return url

    raise RuntimeError(
        "Could not find uploaded video URL in Uguu response:\n"
        + response.text[:2000]
    )


def extract_json(text):
    text = text.strip()

    # Remove markdown fences if model used them
    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    # Direct JSON
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try first JSON array
    start = text.find("[")
    end = text.rfind("]")

    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]

        try:
            return json.loads(candidate)
        except Exception:
            pass

    # Try JSON object
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]

        try:
            return json.loads(candidate)
        except Exception:
            pass

    raise ValueError(
        "Could not extract valid JSON from model response:\n"
        + text[:5000]
    )


def timestamp_to_seconds(value):
    if isinstance(value, (int, float)):
        return float(value)

    if not isinstance(value, str):
        raise ValueError(f"Invalid timestamp: {value}")

    value = value.strip()

    parts = value.split(":")

    if len(parts) == 1:
        return float(parts[0])

    if len(parts) == 2:
        minutes = float(parts[0])
        seconds = float(parts[1])

        return minutes * 60 + seconds

    if len(parts) == 3:
        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])

        return hours * 3600 + minutes * 60 + seconds

    raise ValueError(f"Invalid timestamp: {value}")


def seconds_to_timestamp(seconds):
    seconds = max(0, int(round(seconds)))

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    return f"{minutes:02d}:{secs:02d}"


def normalize_clips(data):
    if isinstance(data, dict):
        if isinstance(data.get("clips"), list):
            data = data["clips"]
        elif isinstance(data.get("shorts"), list):
            data = data["shorts"]
        elif isinstance(data.get("results"), list):
            data = data["results"]
        else:
            data = [data]

    if not isinstance(data, list):
        raise ValueError("Model response is not a list of clips.")

    normalized = []

    for item in data:
        if not isinstance(item, dict):
            continue

        start_value = (
            item.get("start")
            if item.get("start") is not None
            else item.get("start_time")
        )

        end_value = (
            item.get("end")
            if item.get("end") is not None
            else item.get("end_time")
        )

        if start_value is None or end_value is None:
            continue

        try:
            start = timestamp_to_seconds(start_value)
            end = timestamp_to_seconds(end_value)
        except Exception:
            continue

        duration = end - start

        if duration < MIN_DURATION or duration > MAX_DURATION:
            continue

        if start < 0 or end <= start:
            continue

        title = (
            item.get("title")
            or item.get("hook")
            or item.get("description")
            or f"Short {len(normalized) + 1}"
        )

        reason = (
            item.get("reason")
            or item.get("why")
            or item.get("description")
            or ""
        )

        normalized.append({
            "start": seconds_to_timestamp(start),
            "end": seconds_to_timestamp(end),
            "start_seconds": round(start, 2),
            "end_seconds": round(end, 2),
            "duration": round(duration, 2),
            "title": str(title).strip(),
            "reason": str(reason).strip()
        })

    # Sort chronologically
    normalized.sort(key=lambda x: x["start_seconds"])

    # Remove overlapping clips
    final_clips = []

    for clip in normalized:
        overlaps = False

        for existing in final_clips:
            if (
                clip["start_seconds"] < existing["end_seconds"]
                and clip["end_seconds"] > existing["start_seconds"]
            ):
                overlaps = True
                break

        if not overlaps:
            final_clips.append(clip)

    # Limit only after quality/validation filtering
    return final_clips[:MAX_CLIPS]


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print(" QWEN VIDEO ANALYSIS ")
    print("=" * 60)

    print(f"Video: {VIDEO_PATH}")
    print(f"Model: {MODEL}")
    print("=" * 60)

    api_key = os.environ.get("OPENROUTER_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY environment variable is missing."
        )

    # --------------------------------------------------------
    # Check video
    # --------------------------------------------------------

    if not os.path.exists(VIDEO_PATH):
        raise FileNotFoundError(
            f"Input video does not exist: {VIDEO_PATH}"
        )

    local_size = os.path.getsize(VIDEO_PATH)

    if local_size == 0:
        raise RuntimeError(
            "Input video exists but is 0 bytes."
        )

    print(
        f"Size: {local_size / (1024 * 1024):.2f} MB"
    )

    # --------------------------------------------------------
    # Upload
    # --------------------------------------------------------

    video_url = upload_video(VIDEO_PATH)

    print("Temporary video URL created.")

    # --------------------------------------------------------
    # Prompt
    # --------------------------------------------------------

    prompt = r"""
You are an expert short-form video editor.

Analyze the ENTIRE supplied video carefully.

Your job is NOT to divide the video into arbitrary pieces.

Find only genuinely strong, self-contained moments that can work as
standalone YouTube Shorts.

QUALITY IS MORE IMPORTANT THAN QUANTITY.

If there are only 3 excellent moments, return only 3.
If there are no excellent moments, return an empty array.

STRICT REQUIREMENTS:

1. Every clip must be between 30 and 60 seconds.
2. Every clip must contain a meaningful, interesting, or entertaining moment.
3. Every clip must make sense when watched by itself.
4. Do not create arbitrary 30-60 second windows.
5. Do not simply split the video into equal sections.
6. Do not create filler clips.
7. Do not create clips just to reach a quota.
8. Do not create multiple clips around the same moment.
9. Clips must not overlap.
10. Avoid repetitive clips.
11. Prefer moments with a strong hook, payoff, surprising event,
    funny interaction, useful information, emotional reaction,
    impressive action, conflict, reveal, or other clear reason
    someone would keep watching.
12. Start as close as possible to the beginning of the meaningful moment.
13. End after the payoff or natural conclusion.
14. Do not invent events.
15. Do not invent timestamps.
16. Timestamps must correspond to the actual supplied video.
17. Analyze the full video before selecting clips.

Return ONLY valid JSON.

Use exactly this format:

[
  {
    "start": "MM:SS",
    "end": "MM:SS",
    "title": "Short descriptive title",
    "reason": "Why this exact moment works as a standalone Short"
  }
]

If there are no strong moments:

[]

Do not include markdown.
Do not include explanations outside the JSON.
"""

    # --------------------------------------------------------
    # Request
    # --------------------------------------------------------

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "video_url",
                        "video_url": {
                            "url": video_url
                        }
                    }
                ]
            }
        ],
        "temperature": 0.2,
        "max_tokens": 8000
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/mo4nt2an0a/shorts-auto",
        "X-Title": "Shorts Auto"
    }

    print()
    print("=" * 60)
    print(" SENDING VIDEO TO OPENROUTER ")
    print("=" * 60)
    print(f"Model: {MODEL}")
    print()

    # --------------------------------------------------------
    # Retry for temporary provider errors
    # --------------------------------------------------------

    max_attempts = 4

    response = None

    for attempt in range(1, max_attempts + 1):

        print(
            f"Attempt {attempt}/{max_attempts}..."
        )

        try:
            response = requests.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
                timeout=900
            )

        except requests.RequestException as e:

            print(f"Request error: {e}")

            if attempt < max_attempts:
                wait = attempt * 15

                print(
                    f"Retrying in {wait} seconds..."
                )

                time.sleep(wait)
                continue

            raise

        print(
            f"OpenRouter HTTP status: {response.status_code}"
        )

        # Success at HTTP level
        if response.status_code == 200:

            try:
                response_json = response.json()
            except Exception:
                response_json = {}

            # OpenRouter can return HTTP 200 with provider error
            if response_json.get("error"):

                error = response_json.get("error", {})

                print()
                print("OpenRouter/provider error:")
                print(json.dumps(error, indent=2))

                error_message = str(
                    error.get("message", "")
                ).lower()

                temporary_errors = [
                    "resourceexhausted",
                    "provider_unavailable",
                    "rate limit",
                    "temporarily",
                    "overloaded",
                    "worker"
                ]

                is_temporary = any(
                    phrase in error_message
                    for phrase in temporary_errors
                )

                if is_temporary and attempt < max_attempts:

                    wait = attempt * 20

                    print(
                        f"Temporary provider problem. "
                        f"Retrying in {wait} seconds..."
                    )

                    time.sleep(wait)
                    continue

                raise RuntimeError(
                    "OpenRouter provider returned an error:\n"
                    + json.dumps(error, indent=2)
                )

            break

        # HTTP error
        if response.status_code in (429, 500, 502, 503, 504):

            if attempt < max_attempts:

                wait = attempt * 20

                print(
                    f"Temporary HTTP error. "
                    f"Retrying in {wait} seconds..."
                )

                time.sleep(wait)
                continue

        # Permanent error
        try:
            error_data = response.json()
        except Exception:
            error_data = response.text

        raise RuntimeError(
            "OpenRouter request failed:\n"
            + json.dumps(error_data, indent=2)
            if isinstance(error_data, dict)
            else str(error_data)
        )

    # --------------------------------------------------------
    # Extract model response
    # --------------------------------------------------------

    try:
        response_json = response.json()
    except Exception:
        raise RuntimeError(
            "OpenRouter returned invalid JSON:\n"
            + response.text[:5000]
        )

    choices = response_json.get("choices")

    if not choices:
        raise RuntimeError(
            "Could not find choices in OpenRouter response:\n"
            + json.dumps(response_json, indent=2)[:10000]
        )

    message = choices[0].get("message", {})
    content = message.get("content")

    if not content:
        raise RuntimeError(
            "Could not find model message content in OpenRouter response:\n"
            + json.dumps(response_json, indent=2)[:10000]
        )

    print()
    print("=" * 60)
    print(" MODEL RESPONSE ")
    print("=" * 60)
    print(content)

    # --------------------------------------------------------
    # Parse JSON
    # --------------------------------------------------------

    raw_data = extract_json(content)

    clips = normalize_clips(raw_data)

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    result = {
        "model": MODEL,
        "video": VIDEO_PATH,
        "clips_found": len(clips),
        "clips": clips
    }

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            result,
            f,
            indent=2,
            ensure_ascii=False
        )

    print()
    print("=" * 60)
    print(" RESULTS ")
    print("=" * 60)

    print(
        f"Valid clips found: {len(clips)}"
    )

    for index, clip in enumerate(clips, 1):

        print(
            f"{index}. "
            f"{clip['start']} -> {clip['end']} "
            f"({clip['duration']}s) "
            f"{clip['title']}"
        )

    print()
    print(
        f"Saved to: {OUTPUT_PATH}"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()
