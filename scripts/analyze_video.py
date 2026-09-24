import os
import sys
import json
import time
from google import genai

API_KEY = os.environ["GEMINI_API_KEY"]

if len(sys.argv) < 2:
    raise RuntimeError(
        "Usage: python scripts/analyze_video.py <video_path>"
    )

VIDEO_PATH = sys.argv[1]

if not os.path.exists(VIDEO_PATH):
    raise FileNotFoundError(VIDEO_PATH)

print(f"Uploading video to Gemini Files API: {VIDEO_PATH}")

client = genai.Client(api_key=API_KEY)

video_file = client.files.upload(
    file=VIDEO_PATH
)

print(f"Uploaded: {video_file.name}")
print(f"Initial state: {video_file.state}")

while (
    not video_file.state
    or video_file.state.name != "ACTIVE"
):
    print("Gemini is processing the video...")

    if video_file.state:
        print(f"File state: {video_file.state.name}")

        if video_file.state.name == "FAILED":
            raise RuntimeError(
                "Gemini failed to process the uploaded video."
            )

    time.sleep(5)

    video_file = client.files.get(
        name=video_file.name
    )

print("Video is ACTIVE and ready for analysis.")

prompt = """
Analyze the ENTIRE video as a professional short-form video editor.

Your job is to find the strongest COMPLETE moments that can become
standalone YouTube Shorts.

IMPORTANT:

- Analyze the entire video before selecting clips.
- Do NOT simply divide the video into equal pieces.
- Do NOT create clips just to increase the number of clips.
- Do NOT make many tiny clips from one conversation or one moment.
- The preferred length is approximately 30-60 seconds.
- A clip can be shorter than 30 seconds ONLY when it is genuinely
  complete, self-contained, and especially strong.
- A clip can be longer than 60 seconds when additional context is
  necessary to make the moment complete.
- Never cut someone off in the middle of an important sentence,
  explanation, story, joke, reaction, or action.
- Include enough setup before the payoff.
- Include the complete payoff.
- Start at a natural point.
- End at a natural point.
- Avoid unnecessary silence or dead space.
- Avoid duplicate or nearly identical clips.
- Clips must not overlap unless there is an exceptional reason.
- Do not force a specific number of clips.
- One excellent clip is better than five weak clips.
- If only one genuinely strong moment exists, return one clip.
- If there are no genuinely strong standalone moments, return zero clips.
- Quality is MUCH more important than quantity.

Think about each potential clip as if it were going to be published
as a standalone YouTube Short.

A viewer who has never seen the original video should understand the
moment without needing the rest of the video.

For every selected clip provide:

- start: exact start time in seconds
- end: exact end time in seconds
- reason: why the COMPLETE moment is valuable
- hook: short compelling hook/title

Return ONLY valid JSON.

Do NOT use Markdown.
Do NOT use ```json.
Do NOT add any text before or after the JSON.

Use exactly this format:

{
  "clips": [
    {
      "start": 12.5,
      "end": 54.8,
      "reason": "Complete moment with setup, useful information and payoff.",
      "hook": "The trick most people don't know"
    }
  ]
}
"""

print("Sending video to Gemini for full-video analysis...")

response = client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents=[
        video_file,
        prompt
    ]
)

text = response.text.strip()

print("===== GEMINI RESPONSE =====")
print(text)

if text.startswith("```"):
    lines = text.splitlines()

    if lines and lines[0].strip().startswith("```"):
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
        "Gemini JSON does not contain a 'clips' field."
    )

if not isinstance(parsed["clips"], list):
    raise RuntimeError(
        "'clips' must be a list."
    )

validated_clips = []

for index, clip in enumerate(
    parsed["clips"],
    start=1
):
    required = [
        "start",
        "end",
        "reason",
        "hook"
    ]

    for field in required:
        if field not in clip:
            raise RuntimeError(
                f"Clip {index} is missing field: {field}"
            )

    start = float(clip["start"])
    end = float(clip["end"])

    if start < 0:
        raise RuntimeError(
            f"Clip {index} has negative start time."
        )

    if end <= start:
        raise RuntimeError(
            f"Clip {index} has invalid timestamps."
        )

    validated_clips.append(
        {
            "start": start,
            "end": end,
            "reason": str(clip["reason"]),
            "hook": str(clip["hook"])
        }
    )

parsed["clips"] = validated_clips

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

print()
print("===== VIDEO ANALYSIS COMPLETE =====")
print(f"Clips found: {len(validated_clips)}")
print("Saved to clips.json")

for index, clip in enumerate(
    validated_clips,
    start=1
):
    duration = clip["end"] - clip["start"]

    print(
        f"Clip {index}: "
        f"{clip['start']:.2f}s -> "
        f"{clip['end']:.2f}s "
        f"({duration:.2f}s)"
    )
    print(f"Hook: {clip['hook']}")