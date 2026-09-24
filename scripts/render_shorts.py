import json
import os
import subprocess

VIDEO = "input/VID_20260921_015943_064.mp4"
OUTPUT_DIR = "output"

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open("clips.json", "r", encoding="utf-8") as f:
    data = json.load(f)

clips = data.get("clips", [])

if not clips:
    raise RuntimeError("No clips found in clips.json")

for index, clip in enumerate(clips, start=1):
    start = float(clip["start"])
    end = float(clip["end"])

    duration = end - start

    if duration <= 0:
        print(f"Skipping clip {index}: invalid duration")
        continue

    output = os.path.join(
        OUTPUT_DIR,
        f"short_{index:02d}.mp4"
    )

    print(
        f"Rendering clip {index}: "
        f"{start:.2f}s -> {end:.2f}s"
    )

    command = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-i", VIDEO,
        "-t", str(duration),

        "-vf",
        (
            "scale=1080:1920:"
            "force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
        ),

        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",

        "-c:a", "aac",
        "-b:a", "128k",

        "-movflags", "+faststart",

        output
    ]

    subprocess.run(command, check=True)

    print(f"Created: {output}")

print()
print(f"Finished rendering {len(clips)} clips.")
