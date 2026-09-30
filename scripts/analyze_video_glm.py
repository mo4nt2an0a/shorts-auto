import json
import os
import sys
import requests


# =========================================================
# CONFIG
# =========================================================

VIDEO_PATH = sys.argv[1] if len(sys.argv) > 1 else "input/MASTER.mp4"

OUTPUT_FILE = "clips_glm.json"

MIN_DURATION = 30
MAX_DURATION = 60
MAX_CLIPS = 20

MODEL = "z-ai/glm-5.3-flash:free"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

UGUU_URL = "https://uguu.se/upload"


# =========================================================
# CHECK VIDEO
# =========================================================

if not os.path.exists(VIDEO_PATH):
    raise RuntimeError(
        f"ERROR: Video not found: {VIDEO_PATH}"
    )


video_size = os.path.getsize(VIDEO_PATH)


print("========================================")
print("GLM 5.3 FLASH VIDEO ANALYSIS")
print("========================================")
print(f"Video: {VIDEO_PATH}")
print(f"Size: {video_size / 1024 / 1024:.2f} MB")
print(f"Model: {MODEL}")
print()


# =========================================================
# CHECK API KEY
# =========================================================

api_key = os.environ.get("OPENROUTER_API_KEY")


if not api_key:
    raise RuntimeError(
        "ERROR: OPENROUTER_API_KEY GitHub Secret is missing."
    )


# =========================================================
# CHECK FILE SIZE
# =========================================================

if video_size > 128 * 1024 * 1024:
    raise RuntimeError(
        "ERROR: Video is larger than 128 MB.\n"
        "The temporary upload used by this test has a 128 MB limit."
    )


# =========================================================
# UPLOAD VIDEO
# =========================================================

print("Uploading video to temporary public URL...")
print()


try:

    with open(VIDEO_PATH, "rb") as video_file:

        upload_response = requests.post(
            UGUU_URL,
            files={
                "files[]": (
                    os.path.basename(VIDEO_PATH),
                    video_file,
                    "video/mp4"
                )
            },
            timeout=300
        )

except requests.RequestException as error:

    raise RuntimeError(
        f"ERROR: Video upload failed: {error}"
    )


if upload_response.status_code != 200:

    print(upload_response.text[:3000])

    raise RuntimeError(
        f"ERROR: Upload server returned HTTP "
        f"{upload_response.status_code}"
    )


try:

    upload_data = upload_response.json()

except ValueError as error:

    raise RuntimeError(
        "ERROR: Upload server returned invalid JSON."
    ) from error


files = upload_data.get("files", [])


if not files:

    raise RuntimeError(
        "ERROR: Upload did not return a file."
    )


video_url = files[0].get("url")


if not video_url:

    raise RuntimeError(
        "ERROR: Upload response does not contain a URL."
    )


print("Temporary video URL created.")
print()


# =========================================================
# ANALYSIS PROMPT
# =========================================================

prompt = f"""
You are an expert short-form video editor.

Analyze the ENTIRE uploaded video from beginning to end.

The goal is to find genuinely strong moments that can become
standalone YouTube Shorts.

QUALITY IS MORE IMPORTANT THAN QUANTITY.

Do NOT select random time ranges.

Do NOT select clips just because you need a certain number.

=========================================================
CLIP REQUIREMENTS
=========================================================

Every selected clip MUST:

1. Be between {MIN_DURATION} and {MAX_DURATION} seconds.

2. Be a complete, coherent moment.

3. Have a clear beginning, middle and ending.

4. Make sense when watched without the original video.

5. Contain enough context for the viewer to understand what is happening.

6. Start at a natural point.

7. End at a natural point.

8. Avoid starting in the middle of a sentence.

9. Avoid ending in the middle of a sentence.

10. Avoid cutting off important action.

11. Have a strong hook, surprising moment, funny moment,
    dramatic moment, reaction, conflict, reveal, payoff,
    emotional moment, unusual situation or strong curiosity.

12. Be substantially different from every other selected clip.

13. NOT overlap with another selected clip.

14. NOT be filler, silence, dead air, walking footage,
    meaningless transitions or setup without payoff.

15. NOT depend on information from many minutes earlier
    unless the clip itself contains enough context.

=========================================================
FULL VIDEO COVERAGE
=========================================================

Analyze the COMPLETE video.

Search:

- opening
- early sections
- middle sections
- later sections
- ending

Do NOT focus only on the beginning.

=========================================================
TIMESTAMP ACCURACY
=========================================================

Use timestamps from the ACTUAL uploaded video.

Do NOT invent timestamps.

Do NOT use arbitrary 30, 45 or 60 second windows.

Start near the natural beginning of the interesting event.

End after the natural payoff or conclusion.

Include necessary context immediately before the main event.

Include important reaction immediately after the event.

=========================================================
QUALITY OVER QUANTITY
=========================================================

There is NO requirement to return {MAX_CLIPS} clips.

If only 5 excellent clips exist, return 5.

If only 2 excellent clips exist, return 2.

If only 1 excellent clip exists, return 1.

If no genuinely strong moments exist, return:

{{"clips":[]}}

NEVER lower the quality threshold.

=========================================================
DUPLICATES
=========================================================

Do not return:

- overlapping clips
- multiple versions of the same event
- short and long versions of the same event
- clips with essentially identical content

Every clip must represent a different moment.

=========================================================
RANKING
=========================================================

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

Use EXACTLY this structure:

{{
  "clips": [
    {{
      "start": 123.45,
      "end": 167.80,
      "reason": "Why this complete moment works as a standalone Short.",
      "hook": "Short attention-grabbing hook."
    }}
  ]
}}

Rules:

- start must be seconds.
- end must be seconds.
- end must be greater than start.
- duration must be between {MIN_DURATION} and {MAX_DURATION} seconds.
- reason must explain why the moment is worth watching.
- hook must be short and attention-grabbing.
- Do not include any other fields.
- No markdown.
- No explanation outside JSON.
"""


# =========================================================
# OPENROUTER REQUEST
# =========================================================

print("========================================")
print("SENDING VIDEO TO OPENROUTER")
print("========================================")
print(f"Model: {MODEL}")
print()


headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://github.com/mo4nt2an0a/shorts-auto",
    "X-OpenRouter-Title": "Shorts Auto"
}


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
    "temperature": 0.1,
    "max_tokens": 8000
}


try:

    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=payload,
        timeout=1800
    )

except requests.RequestException as error:

    raise RuntimeError(
        f"ERROR: OpenRouter request failed: {error}"
    )


print(
    f"OpenRouter HTTP status: {response.status_code}"
)
print()


# =========================================================
# HANDLE API ERROR
# =========================================================

if response.status_code != 200:

    print("===== OPENROUTER ERROR =====")
    print(response.text[:5000])
    print("============================")

    raise RuntimeError(
        f"ERROR: OpenRouter returned HTTP "
        f"{response.status_code}"
    )


# =========================================================
# READ RESPONSE
# =========================================================

try:

    response_data = response.json()

except ValueError as error:

    raise RuntimeError(
        "ERROR: OpenRouter returned invalid JSON."
    ) from error


try:

    raw_response = (
        response_data["choices"][0]["message"]["content"]
        .strip()
    )

except (KeyError, IndexError, TypeError) as error:

    print(
        json.dumps(
            response_data,
            indent=2,
            ensure_ascii=False
        )
    )

    raise RuntimeError(
        "ERROR: Could not find model response."
    ) from error


print("========================================")
print("GLM RESPONSE")
print("========================================")
print(raw_response)
print("========================================")
print()


# =========================================================
# CLEAN MARKDOWN CODE FENCES
# =========================================================

cleaned = raw_response.strip()


if cleaned.startswith("```"):

    lines = cleaned.splitlines()

    if lines and lines[0].startswith("```"):
        lines = lines[1:]

    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    cleaned = "\n".join(lines).strip()


# =========================================================
# PARSE JSON
# =========================================================

try:

    data = json.loads(cleaned)

except json.JSONDecodeError:

    start_index = cleaned.find("{")
    end_index = cleaned.rfind("}")

    if start_index == -1 or end_index == -1:

        raise RuntimeError(
            "ERROR: GLM did not return valid JSON."
        )

    try:

        data = json.loads(
            cleaned[start_index:end_index + 1]
        )

    except json.JSONDecodeError as error:

        raise RuntimeError(
            "ERROR: GLM response could not be parsed as JSON."
        ) from error


# =========================================================
# VALIDATE STRUCTURE
# =========================================================

clips = data.get("clips")


if not isinstance(clips, list):

    raise RuntimeError(
        "ERROR: GLM JSON does not contain a valid 'clips' list."
    )


# =========================================================
# VALIDATE CLIPS
# =========================================================

valid_clips = []


for index, clip in enumerate(clips, start=1):

    if not isinstance(clip, dict):

        print(
            f"Skipping clip {index}: not an object."
        )

        continue


    try:

        start = float(clip["start"])
        end = float(clip["end"])

    except (KeyError, TypeError, ValueError):

        print(
            f"Skipping clip {index}: invalid timestamps."
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
            f"{duration:.2f}s < {MIN_DURATION}s."
        )

        continue


    if duration > MAX_DURATION:

        print(
            f"Skipping clip {index}: "
            f"{duration:.2f}s > {MAX_DURATION}s."
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
# SORT BY START
# =========================================================

valid_clips.sort(
    key=lambda clip: clip["start"]
)


# =========================================================
# REMOVE OVERLAPS
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


        print("Overlap detected.")


        if current_duration > previous_duration:

            print(
                "Keeping new longer clip."
            )

            non_overlapping[-1] = clip

        else:

            print(
                "Keeping existing longer clip."
            )

    else:

        non_overlapping.append(clip)


valid_clips = non_overlapping


# =========================================================
# LIMIT NUMBER OF CLIPS
# =========================================================

if len(valid_clips) > MAX_CLIPS:

    valid_clips = valid_clips[:MAX_CLIPS]


# =========================================================
# SAVE RESULT
# =========================================================

final_data = {
    "clips": valid_clips
}


with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as output_file:

    json.dump(
        final_data,
        output_file,
        indent=2,
        ensure_ascii=False
    )


# =========================================================
# FINAL REPORT
# =========================================================

print()
print("========================================")
print("GLM ANALYSIS COMPLETE")
print("========================================")
print(
    f"Clips returned by GLM: {len(clips)}"
)
print(
    f"Valid clips saved:     {len(valid_clips)}"
)
print(
    f"Output:                {OUTPUT_FILE}"
)
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

    print(
        "No valid high-quality clips found."
    )
