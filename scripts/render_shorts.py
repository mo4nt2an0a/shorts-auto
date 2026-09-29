import json
import os
import subprocess
import sys


VIDEO = "input/MASTER.mp4"
OUTPUT_DIR = "output"

# Target Shorts duration.
MIN_DURATION = 15.0
MAX_DURATION = 60.0

os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_command(command):
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        print("COMMAND FAILED:")
        print(" ".join(command))
        print(result.stderr)
        return False

    return True


def get_video_duration(path):
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        path
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        return None

    try:
        return float(result.stdout.strip())
    except (ValueError, TypeError):
        return None


def validate_video(path):
    if not os.path.exists(path):
        print(f"INVALID: file does not exist: {path}")
        return False

    if os.path.getsize(path) < 10000:
        print(f"INVALID: file is suspiciously small: {path}")
        return False

    duration = get_video_duration(path)

    if duration is None:
        print(f"INVALID: ffprobe could not read: {path}")
        return False

    print(
        f"Validation: {os.path.basename(path)} "
        f"= {duration:.2f}s"
    )

    if duration < MIN_DURATION:
        print(
            f"REJECTED: {os.path.basename(path)} "
            f"is shorter than {MIN_DURATION:.0f}s."
        )
        return False

    if duration > MAX_DURATION + 1.0:
        print(
            f"REJECTED: {os.path.basename(path)} "
            f"is longer than {MAX_DURATION:.0f}s."
        )
        return False

    return True


# ---------------------------------------------------------
# Load Gemini clip analysis
# ---------------------------------------------------------

if not os.path.exists("clips.json"):
    raise RuntimeError("ERROR: clips.json was not found.")

with open("clips.json", "r", encoding="utf-8") as f:
    data = json.load(f)

clips = data.get("clips", [])

if not isinstance(clips, list):
    raise RuntimeError("ERROR: 'clips' in clips.json must be a list.")


if not os.path.exists(VIDEO):
    raise RuntimeError(f"ERROR: Source video not found: {VIDEO}")


# ---------------------------------------------------------
# Get source video duration
# ---------------------------------------------------------

source_duration = get_video_duration(VIDEO)

if source_duration is None:
    raise RuntimeError(
        "ERROR: Could not determine source video duration."
    )

print("========================================")
print("SHORTS RENDERER")
print("========================================")
print(f"Source video: {VIDEO}")
print(f"Source duration: {source_duration:.2f}s")
print(f"Allowed Short duration: {MIN_DURATION:.0f}-{MAX_DURATION:.0f}s")
print(f"Gemini clips received: {len(clips)}")
print("========================================")


# ---------------------------------------------------------
# Remove old generated Shorts
# ---------------------------------------------------------

for filename in os.listdir(OUTPUT_DIR):
    if filename.lower().endswith(".mp4"):
        old_path = os.path.join(OUTPUT_DIR, filename)

        try:
            os.remove(old_path)
            print(f"Removed old output: {old_path}")
        except Exception as error:
            print(
                f"WARNING: Could not remove old file "
                f"{old_path}: {error}"
            )


# ---------------------------------------------------------
# Validate and render clips
# ---------------------------------------------------------

created_files = []
rejected_count = 0

for index, clip in enumerate(clips, start=1):

    try:
        start = float(clip["start"])
        end = float(clip["end"])
    except (KeyError, TypeError, ValueError):
        print(
            f"Skipping clip {index}: "
            "invalid start/end values."
        )
        rejected_count += 1
        continue

    duration = end - start

    print()
    print("----------------------------------------")
    print(f"Clip {index}")
    print(f"Requested: {start:.2f}s -> {end:.2f}s")
    print(f"Duration: {duration:.2f}s")

    # Basic timestamp validation.
    if start < 0:
        print("REJECTED: start time is negative.")
        rejected_count += 1
        continue

    if end <= start:
        print("REJECTED: end time is not after start time.")
        rejected_count += 1
        continue

    # Do not allow Gemini to request beyond the source.
    if start >= source_duration:
        print("REJECTED: start is beyond source video.")
        rejected_count += 1
        continue

    if end > source_duration:
        print(
            "REJECTED: end time is beyond source video."
        )
        rejected_count += 1
        continue

    # Hard Shorts duration guard.
    if duration < MIN_DURATION:
        print(
            f"REJECTED: {duration:.2f}s is below "
            f"minimum {MIN_DURATION:.0f}s."
        )
        rejected_count += 1
        continue

    if duration > MAX_DURATION:
        print(
            f"REJECTED: {duration:.2f}s is above "
            f"maximum {MAX_DURATION:.0f}s."
        )
        rejected_count += 1
        continue

    output = os.path.join(
        OUTPUT_DIR,
        f"short_{len(created_files) + 1:02d}.mp4"
    )

    command = [
        "ffmpeg",
        "-y",

        # Accurate seeking.
        "-ss",
        f"{start:.3f}",

        "-i",
        VIDEO,

        "-t",
        f"{duration:.3f}",

        "-vf",
        (
            "scale=1080:1920:"
            "force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
        ),

        "-c:v",
        "libx264",

        "-preset",
        "fast",

        "-crf",
        "23",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-ar",
        "44100",

        "-movflags",
        "+faststart",

        output
    ]

    print(f"Rendering -> {output}")

    success = run_command(command)

    if not success:
        print(
            f"REJECTED: FFmpeg failed for clip {index}."
        )

        if os.path.exists(output):
            try:
                os.remove(output)
            except Exception:
                pass

        rejected_count += 1
        continue

    # -----------------------------------------------------
    # Verify the actual generated MP4
    # -----------------------------------------------------

    actual_duration = get_video_duration(output)

    if actual_duration is None:
        print(
            f"REJECTED: generated file could not be "
            f"read by ffprobe: {output}"
        )

        try:
            os.remove(output)
        except Exception:
            pass

        rejected_count += 1
        continue

    print(
        f"Actual rendered duration: "
        f"{actual_duration:.2f}s"
    )

    if actual_duration < MIN_DURATION:
        print(
            f"REJECTED: actual output is shorter than "
            f"{MIN_DURATION:.0f}s."
        )

        try:
            os.remove(output)
        except Exception:
            pass

        rejected_count += 1
        continue

    if actual_duration > MAX_DURATION + 1.0:
        print(
            f"REJECTED: actual output is longer than "
            f"{MAX_DURATION:.0f}s."
        )

        try:
            os.remove(output)
        except Exception:
            pass

        rejected_count += 1
        continue

    # -----------------------------------------------------
    # Final integrity check
    # -----------------------------------------------------

    integrity_command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        output,
        "-f",
        "null",
        "-"
    ]

    integrity = subprocess.run(
        integrity_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if integrity.returncode != 0:
        print(
            f"REJECTED: generated MP4 failed integrity check: "
            f"{output}"
        )
        print(integrity.stderr)

        try:
            os.remove(output)
        except Exception:
            pass

        rejected_count += 1
        continue

    print(f"ACCEPTED: {output}")

    created_files.append(output)


# ---------------------------------------------------------
# Final result
# ---------------------------------------------------------

print()
print("========================================")
print("RENDERING COMPLETE")
print("========================================")
print(f"Accepted Shorts: {len(created_files)}")
print(f"Rejected clips:  {rejected_count}")

if created_files:
    print()
    print("Generated files:")

    for path in created_files:
        duration = get_video_duration(path)

        print(
            f"  {os.path.basename(path)} "
            f"({duration:.2f}s)"
        )

else:
    print()
    print(
        "NO VALID SHORTS WERE CREATED."
    )
    print(
        "Gemini did not provide any clips inside "
        f"the allowed {MIN_DURATION:.0f}-{MAX_DURATION:.0f}s range."
    )

    # Fail the workflow instead of uploading an empty/bad artifact.
    sys.exit(1)

print("========================================")
