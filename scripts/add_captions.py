import glob
import os
import re
import subprocess

from faster_whisper import WhisperModel


INPUT_DIR = "output"

MODEL_SIZE = "small.en"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

FONT_NAME = "Arial"
FONT_SIZE = 16

# Maksimālais vārdu skaits vienā caption blokā
MAX_WORDS = 5

# Maksimālais rakstzīmju skaits vienā caption blokā
MAX_CHARS = 30


videos = sorted(
    glob.glob(os.path.join(INPUT_DIR, "short_*.mp4"))
)

if not videos:
    raise RuntimeError("No Shorts found in output/")


print("========================================")
print("LOADING WHISPER")
print(f"Model:        {MODEL_SIZE}")
print(f"Device:       {DEVICE}")
print(f"Compute type: {COMPUTE_TYPE}")
print("========================================")


model = WhisperModel(
    MODEL_SIZE,
    device=DEVICE,
    compute_type=COMPUTE_TYPE
)


def ass_timestamp(seconds):
    """
    ASS timestamp:
    H:MM:SS.cc
    """

    if seconds < 0:
        seconds = 0

    total_cs = int(round(seconds * 100))

    hours = total_cs // 360000

    minutes = (total_cs % 360000) // 6000

    seconds_part = (total_cs % 6000) // 100

    centiseconds = total_cs % 100

    return (
        f"{hours}:{minutes:02d}:"
        f"{seconds_part:02d}.{centiseconds:02d}"
    )


def clean_word(text):
    text = text.strip()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


def build_caption_chunks(words):
    """
    Convert Whisper word timestamps into readable
    short caption chunks.

    Each chunk:
    - max 5 words
    - max 30 characters
    - follows actual word timing
    """

    chunks = []

    current_words = []
    current_chars = 0

    for word in words:

        text = clean_word(word.word)

        if not text:
            continue

        if word.start is None or word.end is None:
            continue

        extra_chars = len(text)

        if current_words:
            extra_chars += 1

        would_exceed_words = (
            len(current_words) >= MAX_WORDS
        )

        would_exceed_chars = (
            current_chars + extra_chars > MAX_CHARS
        )

        if current_words and (
            would_exceed_words
            or would_exceed_chars
        ):
            chunks.append(
                {
                    "start": current_words[0]["start"],
                    "end": current_words[-1]["end"],
                    "text": " ".join(
                        item["text"]
                        for item in current_words
                    )
                }
            )

            current_words = []
            current_chars = 0

        current_words.append(
            {
                "text": text,
                "start": float(word.start),
                "end": float(word.end)
            }
        )

        current_chars += extra_chars

    if current_words:
        chunks.append(
            {
                "start": current_words[0]["start"],
                "end": current_words[-1]["end"],
                "text": " ".join(
                    item["text"]
                    for item in current_words
                )
            }
        )

    return chunks


def escape_ass_text(text):
    """
    Escape characters that have special meaning in ASS.
    """

    text = text.replace("\\", r"\\")
    text = text.replace("{", r"\{")
    text = text.replace("}", r"\}")

    return text


def make_ass(chunks, path):
    """
    Create a styled ASS subtitle file.
    """

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "[Script Info]\n"
        )

        f.write(
            "ScriptType: v4.00+\n"
        )

        f.write(
            "PlayResX: 1080\n"
        )

        f.write(
            "PlayResY: 1920\n"
        )

        f.write(
            "ScaledBorderAndShadow: yes\n"
        )

        f.write("\n")

        f.write(
            "[V4+ Styles]\n"
        )

        f.write(
            "Format: Name, "
            "Fontname, Fontsize, PrimaryColour, "
            "SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, "
            "ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        )

        f.write(
            "Style: Shorts,"
            f"{FONT_NAME},"
            f"{FONT_SIZE},"
            "&H00FFFFFF,"
            "&H00FFFFFF,"
            "&H00000000,"
            "&H99000000,"
            "-1,0,0,0,"
            "100,100,0,0,"
            "3,4,2,"
            "2,60,60,250,1\n"
        )

        f.write("\n")

        f.write(
            "[Events]\n"
        )

        f.write(
            "Format: Layer, Start, End, Style, "
            "Name, MarginL, MarginR, MarginV, "
            "Effect, Text\n"
        )

        for chunk in chunks:

            text = escape_ass_text(
                chunk["text"]
            )

            start = ass_timestamp(
                chunk["start"]
            )

            end = ass_timestamp(
                chunk["end"]
            )

            f.write(
                "Dialogue: "
                f"0,{start},{end},"
                f"Shorts,,0,0,0,,"
                f"{text}\n"
            )


def transcribe_video(video):
    print()
    print("========================================")
    print(f"Transcribing: {video}")
    print("========================================")

    segments, info = model.transcribe(
        video,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": 500
        }
    )

    all_words = []

    for segment in segments:

        if not segment.words:
            continue

        for word in segment.words:

            if not word.word:
                continue

            all_words.append(word)

    print(
        f"Detected language: "
        f"{info.language}"
    )

    if info.language_probability is not None:
        print(
            f"Language probability: "
            f"{info.language_probability:.2f}"
        )

    print(
        f"Whisper words: "
        f"{len(all_words)}"
    )

    return all_words


for video in videos:

    print()
    print("########################################")
    print(f"CAPTIONS FOR: {video}")
    print("########################################")

    words = transcribe_video(video)

    if not words:
        print(
            "WARNING: No speech detected. "
            "Leaving video unchanged."
        )
        continue

    chunks = build_caption_chunks(
        words
    )

    if not chunks:
        print(
            "WARNING: No caption chunks created. "
            "Leaving video unchanged."
        )
        continue

    ass_path = video.replace(
        ".mp4",
        ".ass"
    )

    temp = video.replace(
        ".mp4",
        "_captioned.mp4"
    )

    make_ass(
        chunks,
        ass_path
    )

    print(
        f"Caption chunks created: "
        f"{len(chunks)}"
    )

    print(
        f"Subtitle file: {ass_path}"
    )

    command = [
        "ffmpeg",
        "-y",

        "-i",
        video,

        "-vf",
        f"ass={ass_path}",

        "-c:v",
        "libx264",

        "-preset",
        "fast",

        "-crf",
        "20",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "copy",

        "-movflags",
        "+faststart",

        temp
    ]

    print("Burning captions...")

    subprocess.run(
        command,
        check=True
    )

    os.replace(
        temp,
        video
    )

    os.remove(
        ass_path
    )

    print(
        f"Done: {video}"
    )


print()
print("========================================")
print("CAPTIONS COMPLETE")
print(f"Videos processed: {len(videos)}")
print("Model: small.en")
print("Word timestamps: enabled")
print("VAD: enabled")
print("ASS styled captions: enabled")
print("========================================")
