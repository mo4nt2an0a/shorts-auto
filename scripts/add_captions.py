import os
import glob
import subprocess
from faster_whisper import WhisperModel

INPUT_DIR = "output"

videos = sorted(
    glob.glob(os.path.join(INPUT_DIR, "short_*.mp4"))
)

if not videos:
    raise RuntimeError("No Shorts found in output/")

print(f"Found {len(videos)} Shorts")

print("Loading Whisper model...")

model = WhisperModel(
    "tiny",
    device="cpu",
    compute_type="int8"
)


def timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)

    return (
        f"{hours:02d}:{minutes:02d}:"
        f"{secs:02d},{millis:03d}"
    )


def make_srt(segments, path):
    count = 0

    with open(path, "w", encoding="utf-8") as f:
        for segment in segments:
            text = segment.text.strip()

            if not text:
                continue

            count += 1

            f.write(f"{count}\n")

            f.write(
                f"{timestamp(segment.start)} --> "
                f"{timestamp(segment.end)}\n"
            )

            f.write(f"{text}\n\n")

    return count


for video in videos:

    print("")
    print("=" * 60)
    print(f"Creating captions: {video}")
    print("=" * 60)

    srt = video.replace(".mp4", ".srt")
    temp = video.replace(".mp4", "_captioned.mp4")

    try:

        segments, info = model.transcribe(
            video,
            beam_size=1,
            vad_filter=True
        )

        caption_count = make_srt(segments, srt)

        print(f"Detected caption segments: {caption_count}")

        # ---------------------------------------------------------
        # NO SPEECH / EMPTY SRT
        # ---------------------------------------------------------

        if caption_count == 0 or not os.path.exists(srt):

            print(
                f"No usable speech detected in {video}. "
                "Keeping video without captions."
            )

            if os.path.exists(srt):
                os.remove(srt)

            continue

        # ---------------------------------------------------------
        # ADD CAPTIONS WITH FFMPEG
        # ---------------------------------------------------------

        print(f"Burning captions into {video}")

        subtitle_path = os.path.abspath(srt)

        # FFmpeg subtitles filter needs escaped path characters.
        subtitle_filter_path = (
            subtitle_path
            .replace("\\", "/")
            .replace(":", "\\:")
            .replace("'", "\\'")
        )

        command = [
            "ffmpeg",
            "-y",
            "-i",
            video,
            "-vf",
            (
                f"subtitles='{subtitle_filter_path}':"
                "force_style="
                "'FontName=Arial,"
                "FontSize=18,"
                "PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H00000000,"
                "Outline=3,"
                "Alignment=2,"
                "MarginV=180'"
            ),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            temp
        ]

        subprocess.run(command, check=True)

        # ---------------------------------------------------------
        # REPLACE ORIGINAL VIDEO
        # ---------------------------------------------------------

        if os.path.exists(temp):
            os.replace(temp, video)

        if os.path.exists(srt):
            os.remove(srt)

        print(f"Done: {video}")

    except subprocess.CalledProcessError as e:

        print("")
        print(f"WARNING: FFmpeg captions failed for {video}")
        print(f"FFmpeg exit code: {e.returncode}")
        print("Keeping the original video and continuing.")

        if os.path.exists(temp):
            os.remove(temp)

        if os.path.exists(srt):
            os.remove(srt)

        continue

    except Exception as e:

        print("")
        print(f"WARNING: Caption generation failed for {video}")
        print(f"Error: {e}")
        print("Keeping the original video and continuing.")

        if os.path.exists(temp):
            os.remove(temp)

        if os.path.exists(srt):
            os.remove(srt)

        continue


print("")
print("=" * 60)
print("Finished captions for all Shorts.")
print("=" * 60)
