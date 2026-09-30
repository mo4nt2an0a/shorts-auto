import json
import os
import sys
import time

from google import genai
from google.genai import types


# =========================================================
# CONFIG
# =========================================================

VIDEO_PATH = sys.argv[1] if len(sys.argv) > 1 else "input/MASTER.mp4"
OUTPUT_FILE = "clips.json"

MIN_DURATION = 30
MAX_DURATION = 60
MAX_CLIPS = 20
POLL_SECONDS = 5

MODEL = "gemini-3.8-flash"


# =========================================================
# CHECKS
# =========================================================

if not os.path.exists(VIDEO_PATH):
    raise RuntimeError(f"ERROR: Video not found: {VIDEO_PATH}")

api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError(
        "ERROR: GEMINI_API_KEY environment variable is missing."
    )


# =========================================================
# GEMINI CLIENT
# =========================================================

client = genai.Client(api_key=api_key)


# =========================================================
# UPLOAD VIDEO
# =========================================================

print("========================================")
print("GEMINI VIDEO ANALYSIS")
print("========================================")
print(f"Video: {VIDEO_PATH}")
print(f"Model: {MODEL}")
print("Uploading video to Gemini Files API...")

video_file = client.files.upload(
    file=VIDEO_PATH
)

print(f"Uploaded: {video_file.name}")
print(f"Initial state: {video_file.state}")


# =========================================================
# WAIT FOR VIDEO PROCESSING
# =========================================================

while video_file.state == "PROCESSING":

    print("Gemini is processing the video...")
    time.sleep(POLL_SECONDS)

    video_file = client.files.get(
        name=video_file.name
    )

    print(f"File state: {video_file.state}")


if video_file.state != "ACTIVE":
    raise RuntimeError(
        f"ERROR: Gemini video processing failed. "
        f"Final state: {video_file.state}"
    )


print("Video is ACTIVE and ready for analysis.")


# =========================================================
# ANALYSIS PROMPT
# =========================================================

prompt = f"""
You are an expert short-form video editor.

Analyze the ENTIRE uploaded video from beginning to end.

The goal is to find genuinely strong moments that can become
standalone YouTube Shorts.

DO NOT simply select random time ranges.

DO NOT select clips just because you need to produce a certain
number of clips.

QUALITY IS MORE IMPORTANT THAN QUANTITY.

=========================================================
CLIP REQUIREMENTS
=========================================================

Every selected clip MUST:

1. Be between {MIN_DURATION} and {MAX_DURATION} seconds long.

2. Be a complete, coherent moment.

3. Have a clear beginning, middle, and ending.

4. Make sense when watched WITHOUT the rest of the original video.

5. Contain enough context for a viewer to understand what is happening.

6. Start at a natural point.

7. End at a natural point.

8. Avoid starting in the middle of a sentence.

9. Avoid ending in the middle of a sentence.

10. Avoid cutting off an important action.

11. Have a strong hook, surprising moment, funny moment,
    dramatic moment, interesting moment, payoff, reaction,
    conflict, reveal, or other reason someone would keep watching.

12. Be substantially different from every other selected clip.

13. NOT overlap with another selected clip.

14. NOT be a simple introduction, filler, walking footage,
    silence, dead air, setup without payoff, or meaningless transition.

15. NOT depend on information that appeared many minutes earlier
    unless the clip itself contains enough context to understand it.

=========================================================
FULL VIDEO COVERAGE
=========================================================

Analyze the ENTIRE video timeline.

Do not focus only on the beginning.

Search for strong moments in:

- the opening
- early sections
- middle sections
- later sections
- the ending

A 30+ minute video may contain many separate events.

Make a deliberate effort to find the strongest moments throughout
the complete timeline.

=========================================================
TIMESTAMP ACCURACY
=========================================================

Use timestamps based on the ACTUAL CONTENT of the uploaded video.

Do NOT invent timestamps.

Do NOT guess.

Do NOT use arbitrary 15, 30, 45, or 60 second windows.

The start timestamp should be close to the natural beginning
of the interesting event.

The end timestamp should include the natural payoff or conclusion.

If a person begins explaining something important immediately before
the main event, include enough of that explanation to provide context.

If the important reaction happens immediately after the main event,
include that reaction.

=========================================================
CLIP LENGTH
=========================================================

Do NOT artificially extend clips.

A 17-second excellent moment is acceptable.

A 25-second excellent moment is acceptable.

A 42-second excellent moment is acceptable.

A 58-second excellent moment is acceptable.

Do not add boring material merely to approach 60 seconds.

=========================================================
QUANTITY
=========================================================

Find up to {MAX_CLIPS} genuinely strong clips.

There is NO requirement to return {MAX_CLIPS}.

If only 5 excellent clips exist, return 5.

If only 2 excellent clips exist, return 2.

If only 1 excellent clip exists, return 1.

If no strong clips exist, return an empty list.

NEVER lower the quality threshold to increase quantity.

=========================================================
DUPLICATES
=========================================================

Each clip must represent a different moment.

Do not return:

- overlapping clips
- multiple versions of the same event
- a short and long version of the same event
- clips with essentially identical content

=========================================================
RANKING
=========================================================

Rank clips by Shorts potential.

Prefer moments with:

- immediate attention
- strong visual action
- surprising events
- funny reactions
- emotional reactions
- conflict
- reveals
- unusual situations
- satisfying payoffs
- clear storytelling
- strong viewer curiosity

=========================================================
OUTPUT FORMAT
=========================================================

Return ONLY valid JSON.

No markdown.

No code fences.

No explanation outside JSON.

Use EXACTLY this structure:

{{
  "clips": [
    {{
      "start": 123.45,
      "end": 167.80,
      "reason": "Why this complete moment works as a standalone Short.",
      "hook": "Short hook describing the moment."
    }}
  ]
}}

Rules:

- start must be a number representing seconds.
- end must be a number representing seconds.
- end must be greater than start.
- duration must be between {MIN_DURATION} and {MAX_DURATION} seconds.
- reason must explain why the complete moment is worth watching.
- hook must be short and attention-grabbing.
- Do not include any other fields.
"""


# =========================================================
# SEND VIDEO FOR ANALYSIS
# =========================================================

print("========================================")
print("Sending video to Gemini for FULL analysis...")
print("========================================")

response = client.models.generate_content(
    model=MODEL,
    contents=[
        types.Content(
            role="user",
            parts=[
                types.Part(
                    text=prompt
                ),
                types.Part(
                    file_data=types.FileData(
                        file_uri=video_file.uri,
                        mime_type=video_file.mime_type
                    )
                )
            ]
        )
    ],
    config=types.GenerateContentConfig(
        temperature=0.1,
        response_mime_type="application/json"
    )
)


# =========================================================
# READ RESPONSE
# =========================================================

raw_response = response.text.strip()

print()
print("===== GEMINI RESPONSE =====")
print(raw_response)
print("===========================")
print()


# =========================================================
# PARSE JSON
# =========================================================

try:
    data = json.loads(raw_response)

except json.JSONDecodeError as error:

    print("Gemini did not return valid JSON.")
    print(f"JSON error: {error}")

    start_index = raw_response.find("{")
    end_index = raw_response.rfind("}")

    if start_index == -1 or end_index == -1:
        raise RuntimeError(
            "ERROR: Could not find a JSON object in Gemini response."
        )

    cleaned = raw_response[start_index:end_index + 1]

    try:
        data = json.loads(cleaned)

    except json.JSONDecodeError as second_error:
        raise RuntimeError(
            "ERROR: Gemini response could not be parsed as JSON."
        ) from second_error


# =========================================================
# VALIDATE STRUCTURE
# =========================================================

clips = data.get("clips")

if not isinstance(clips, list):
    raise RuntimeError(
        "ERROR: Gemini JSON does not contain a valid 'clips' list."
    )


# =========================================================
# VALIDATE CLIPS
# =========================================================

valid_clips = []

for index, clip in enumerate(clips, start=1):

    if not isinstance(clip, dict):
        print(f"Skipping clip {index}: not an object.")
        continue

    try:
        start = float(clip["start"])
        end = float(clip["end"])

    except (KeyError, TypeError, ValueError):
        print(
            f"Skipping clip {index}: invalid start/end."
        )
        continue

    reason = str(
        clip.get("reason", "")
    ).strip()

    hook = str(
        clip.get("hook", "")
    ).strip()

    duration = end - start

    if start < 0:
        print(
            f"Skipping clip {index}: negative start."
        )
        continue

    if end <= start:
        print(
            f"Skipping clip {index}: invalid duration."
        )
        continue

    if duration < MIN_DURATION:
        print(
            f"Skipping clip {index}: "
            f"{duration:.2f}s is shorter than {MIN_DURATION}s."
        )
        continue

    if duration > MAX_DURATION:
        print(
            f"Skipping clip {index}: "
            f"{duration:.2f}s is longer than {MAX_DURATION}s."
        )
        continue

    if not reason:
        print(
            f"Skipping clip {index}: missing reason."
        )
        continue

    if not hook:
        print(
            f"Skipping clip {index}: missing hook."
        )
        continue

    valid_clips.append(
        {
            "start": round(start, 3),
            "end": round(end, 3),
            "reason": reason,
            "hook": hook
        }
    )


# =========================================================
# SORT BY START TIME
# =========================================================

valid_clips.sort(
    key=lambda clip: clip["start"]
)


# =========================================================
# REMOVE OVERLAPPING CLIPS
# =========================================================

non_overlapping = []

for clip in valid_clips:

    if not non_overlapping:
        non_overlapping.append(clip)
        continue

    previous = non_overlapping[-1]

    if clip["start"] < previous["end"]:

        previous_duration = (
            previous["end"] -
            previous["start"]
        )

        current_duration = (
            clip["end"] -
            clip["start"]
        )

        print("Overlap detected:")
        print(
            f"  Existing: "
            f"{previous['start']:.2f}s -> "
            f"{previous['end']:.2f}s "
            f"({previous_duration:.2f}s)"
        )
        print(
            f"  New: "
            f"{clip['start']:.2f}s -> "
            f"{clip['end']:.2f}s "
            f"({current_duration:.2f}s)"
        )

        if current_duration > previous_duration:
            print("Keeping the new, longer clip.")
            non_overlapping[-1] = clip
        else:
            print("Keeping the existing, longer clip.")

    else:
        non_overlapping.append(clip)


valid_clips = non_overlapping


# =========================================================
# LIMIT FINAL NUMBER
# =========================================================

if len(valid_clips) > MAX_CLIPS:
    valid_clips = valid_clips[:MAX_CLIPS]


# =========================================================
# SAVE
# =========================================================

final_data = {
    "clips": valid_clips
}

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        final_data,
        f,
        indent=2,
        ensure_ascii=False
    )


# =========================================================
# REPORT
# =========================================================

print()
print("========================================")
print("VIDEO ANALYSIS COMPLETE")
print("========================================")
print(f"Clips returned by Gemini: {len(clips)}")
print(f"Valid clips saved:        {len(valid_clips)}")
print(f"Saved to:                 {OUTPUT_FILE}")
print("========================================")

if valid_clips:

    for index, clip in enumerate(
        valid_clips,
        start=1
    ):

        duration = (
            clip["end"] -
            clip["start"]
        )

        print(
            f"Clip {index}: "
            f"{clip['start']:.2f}s -> "
            f"{clip['end']:.2f}s "
            f"({duration:.2f}s)"
        )

        print(
            f"Hook: {clip['hook']}"
        )

else:

    print()
    print(
        "WARNING: Gemini did not find any "
        "valid 15-60 second clips."
    )
    print(
        "No low-quality clips will be created."
    )
