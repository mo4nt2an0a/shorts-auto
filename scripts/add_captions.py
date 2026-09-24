import os
import subprocess
import glob

INPUT_DIR = "output"

videos = sorted(glob.glob(os.path.join(INPUT_DIR, "short_*.mp4")))

if not videos:
    raise RuntimeError("No Shorts found in output/")

for video in videos:
    temp = video.replace(".mp4", "_captioned.mp4")

    print(f"Adding captions to: {video}")

    command = [
        "ffmpeg",
        "-y",
        "-i", video,
        "-vf",
        (
            "drawtext="
            "text='SHORT':"
            "fontcolor=white:"
            "fontsize=72:"
            "borderw=4:"
            "bordercolor=black:"
            "x=(w-text_w)/2:"
            "y=h*0.12"
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

print(f"Captioned {len(videos)} Shorts.")
