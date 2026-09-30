import json
import os
import subprocess

VIDEO = "input/MASTER.mp4"
OUTPUT_DIR = "output"

# "cover" = aizpilda visu 9:16 kadru un apgriež malas
# "contain" = saglabā visu source video ar melnām malām
FIT_MODE = os.environ.get("VIDEO_FIT_MODE", "cover").lower()

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920

os.makedirs(OUTPUT_DIR, exist_ok=True)

if not os.path.isfile(VIDEO):
    raise RuntimeError(f"Source video not found: {VIDEO}")

with open("clips.json", "r", encoding="utf-8") as f:
    data = json.load(f)

clips = data.get("clips", [])

if not clips:
    raise RuntimeError("No clips found in clips.json")

if FIT_MODE not in ("cover", "contain"):
    raise RuntimeError(
        f"Invalid VIDEO_FIT_MODE: {FIT_MODE}. "
        "Use 'cover' or 'contain'."
    )

if FIT_MODE == "cover":
    video_filter = (
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:"
        "force_original_aspect_ratio=increase,"
        f"crop={TARGET_WIDTH}:{TARGET_HEIGHT}"
    )
else:
    video_filter = (
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:"
        "force_original_aspect_ratio=decrease,"
        f"pad={TARGET_WIDTH}:{TARGET_HEIGHT}:"
        "(ow-iw)/2:(oh-ih)/2:black"
    )

created = 0

for index, clip in enumerate(clips, start=1):
    try:
        start = float(clip["start"])
        end = float(clip["end"])
    except (KeyError, TypeError, ValueError) as error:
        print(f"Skipping clip {index}: invalid clip data: {error}")
        continue

    duration = end - start

    if duration <= 0:
        print(f"Skipping clip {index}: invalid duration")
        continue

    output = os.path.join(
        OUTPUT_DIR,
        f"short_{index:02d}.mp4"
    )

    print("========================================")
    print(f"Rendering clip {index}")
    print(f"Start:    {start:.2f}s")
    print(f"End:      {end:.2f}s")
    print(f"Duration: {duration:.2f}s")
    print(f"Fit:      {FIT_MODE}")
    print(f"Output:   {output}")
    print("========================================")

    command = [
        "ffmpeg",
        "-y",

        "-ss",
        str(start),

        "-i",
        VIDEO,

        "-t",
        str(duration),

        "-map",
        "0:v:0",

        "-map",
        "0:a?",

        "-vf",
        video_filter,

        "-c:v",
        "libx264",

        "-preset",
        "fast",

        "-crf",
        "20",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "aac",

        "-b:a",
        "160k",

        "-ar",
        "48000",

        "-movflags",
        "+faststart",

        output
    ]

    subprocess.run(command, check=True)

    if not os.path.isfile(output):
        raise RuntimeError(
            f"FFmpeg reported success but output was not created: {output}"
        )

    created += 1

    print(f"Created: {output}")

print()
print("========================================")
print("RENDERING COMPLETE")
print(f"Clips requested: {len(clips)}")
print(f"Clips created:   {created}")
print(f"Fit mode:        {FIT_MODE}")
print("Resolution:      1080x1920")
print("========================================")

if created == 0:
    raise RuntimeError("No Shorts were successfully rendered.")
