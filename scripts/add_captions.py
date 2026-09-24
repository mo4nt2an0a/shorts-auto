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
    with open(path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(segments, start=1):
            text = segment.text.strip()

            if not text:
                continue

            f.write(f"{i}\n")
            f.write(
                f"{timestamp(segment.start)} --> "
                f"{timestamp(segment.end)}\n"
            )
            f.write(f"{text}\n\n")


for video in videos:
    print(f"Creating captions: {video}")

    srt = video.replace(".mp4", ".srt")
    temp = video.replace(".mp4", "_captioned.mp4")

    segments, info = model.transcribe(
        video,
        beam_size=1,
        vad_filter=True
    )

    make_srt(segments, srt)

    command = [
        "ffmpeg",
        "-y",
        "-i", video,
        "-vf",
        (
            f"subtitles={srt}:"
            "force_style="
            "'FontName=Arial,"
            "FontSize=18,"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "Outline=3,"
            "Alignment=2,"
            "MarginV=180'"
        ),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "copy",
        "-movflags", "+faststart",
        temp
    ]

    subprocess.run(command, check=True)

    os.replace(temp, video)
    os.remove(srt)

    print(f"Done: {video}")

print(f"Finished captions for {len(videos)} Shorts.")
