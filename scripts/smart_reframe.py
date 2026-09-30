import glob
import os
import subprocess
import tempfile

import cv2


INPUT_DIR = "output"

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920

SAMPLE_INTERVAL = float(
    os.environ.get(
        "SMART_REFRAME_INTERVAL",
        "0.25"
    )
)

SMOOTHING = float(
    os.environ.get(
        "SMART_REFRAME_SMOOTHING",
        "0.35"
    )
)

MAX_MOVE_RATIO = float(
    os.environ.get(
        "SMART_REFRAME_MAX_MOVE",
        "0.12"
    )
)


def escape_filter_path(path):
    return (
        path
        .replace("\\", "/")
        .replace("'", r"\'")
        .replace(":", r"\:")
    )


def probe_video(video):
    cap = cv2.VideoCapture(video)

    fps = cap.get(
        cv2.CAP_PROP_FPS
    ) or 30.0

    frames = int(
        cap.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )

    width = int(
        cap.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    height = int(
        cap.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )

    cap.release()

    duration = (
        frames / fps
        if fps
        else 0.0
    )

    return (
        width,
        height,
        fps,
        frames,
        duration
    )


def detect_face_center(
    frame,
    cascade,
    previous_center=None
):
    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    gray = cv2.equalizeHist(
        gray
    )

    scale = 1.0
    work = gray

    if gray.shape[1] > 640:

        scale = (
            640.0 /
            gray.shape[1]
        )

        work = cv2.resize(
            gray,
            (
                640,
                max(
                    2,
                    int(
                        gray.shape[0]
                        * scale
                    )
                )
            ),
            interpolation=cv2.INTER_AREA
        )

    faces = cascade.detectMultiScale(
        work,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(32, 32)
    )

    if len(faces) == 0:
        return None

    candidates = []

    for x, y, w, h in faces:

        center_x = (
            x + w / 2.0
        ) / scale

        center_y = (
            y + h / 2.0
        ) / scale

        area = (
            w * h
        ) / (
            scale * scale
        )

        candidates.append(
            (
                center_x,
                center_y,
                area
            )
        )

    if previous_center is None:

        return max(
            candidates,
            key=lambda item: item[2]
        )

    def score(item):

        center_x = item[0]
        area = item[2]

        distance = abs(
            center_x -
            previous_center
        )

        return (
            area /
            (
                1.0 +
                distance * 0.003
            )
        )

    return max(
        candidates,
        key=score
    )


def make_trajectory(
    video,
    width,
    height,
    fps,
    duration,
    crop_width
):
    cascade_path = (
        cv2.data.haarcascades
        +
        "haarcascade_frontalface_default.xml"
    )

    cascade = cv2.CascadeClassifier(
        cascade_path
    )

    if cascade.empty():

        raise RuntimeError(
            "OpenCV face detector "
            "could not be loaded."
        )

    cap = cv2.VideoCapture(
        video
    )

    if not cap.isOpened():

        raise RuntimeError(
            f"Could not open {video}"
        )

    positions = []

    previous_center = (
        width / 2.0
    )

    last_detection_time = -999.0

    frame_index = 0
    next_sample = 0.0

    max_move = max(
        8.0,
        crop_width *
        MAX_MOVE_RATIO
    )

    try:

        while True:

            ok, frame = (
                cap.read()
            )

            if not ok:
                break

            timestamp = (
                frame_index /
                fps
            )

            if (
                timestamp + 1e-6
                >= next_sample
            ):

                result = (
                    detect_face_center(
                        frame,
                        cascade,
                        previous_center
                    )
                )

                if result is not None:

                    detected_x = (
                        result[0]
                    )

                    target = max(
                        crop_width / 2.0,
                        min(
                            width -
                            crop_width / 2.0,
                            detected_x
                        )
                    )

                    delta = (
                        target -
                        previous_center
                    )

                    delta = max(
                        -max_move,
                        min(
                            max_move,
                            delta
                        )
                    )

                    target = (
                        previous_center
                        + delta
                    )

                    previous_center = (
                        previous_center
                        * (
                            1.0 -
                            SMOOTHING
                        )
                        +
                        target
                        * SMOOTHING
                    )

                    last_detection_time = (
                        timestamp
                    )

                positions.append(
                    (
                        timestamp,
                        previous_center
                    )
                )

                next_sample += (
                    SAMPLE_INTERVAL
                )

            frame_index += 1

    finally:

        cap.release()

    if not positions:

        return (
            [],
            False
        )

    detected_any = (
        last_detection_time
        >= 0.0
    )

    return (
        positions,
        detected_any
    )


def write_sendcmd(
    path,
    positions,
    crop_width,
    width
):
    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        for timestamp, center in positions:

            x = int(
                round(
                    center -
                    crop_width / 2.0
                )
            )

            x = max(
                0,
                min(
                    width -
                    crop_width,
                    x
                )
            )

            f.write(
                f"{timestamp:.4f} "
                f"crop@smart x {x};\n"
            )


def reframe(video):

    (
        width,
        height,
        fps,
        frames,
        duration
    ) = probe_video(
        video
    )

    if (
        width <= 0
        or height <= 0
        or frames <= 0
    ):

        print(
            f"SKIP {video}: "
            "invalid video"
        )

        return False

    aspect = (
        width /
        float(height)
    )

    # Already vertical.
    if aspect <= 0.60:

        print(
            f"SKIP {video}: "
            f"already vertical "
            f"({width}x{height})"
        )

        return False

    crop_width = int(
        round(
            height *
            9.0 /
            16.0
        )
    )

    if crop_width >= width:

        print(
            f"SKIP {video}: "
            "source too narrow "
            "for 9:16 crop"
        )

        return False

    print(
        "=" * 50
    )

    print(
        f"SMART REFRAME: {video}"
    )

    print(
        f"Source: "
        f"{width}x{height} "
        f"@ {fps:.2f} fps"
    )

    print(
        f"Crop: "
        f"{crop_width}x{height}"
    )

    print(
        "=" * 50
    )

    (
        positions,
        detected
    ) = make_trajectory(
        video,
        width,
        height,
        fps,
        duration,
        crop_width
    )

    if not detected:

        print(
            "No face detected."
        )

        print(
            "Keeping existing "
            "center crop."
        )

        return False

    workdir = tempfile.mkdtemp(
        prefix="smart_reframe_"
    )

    cmd_path = os.path.join(
        workdir,
        "crop.txt"
    )

    temp_output = os.path.join(
        workdir,
        "reframed.mp4"
    )

    try:

        write_sendcmd(
            cmd_path,
            positions,
            crop_width,
            width
        )

        safe_cmd_path = (
            escape_filter_path(
                cmd_path
            )
        )

        initial_x = int(
            round(
                positions[0][1]
                -
                crop_width / 2.0
            )
        )

        initial_x = max(
            0,
            min(
                width -
                crop_width,
                initial_x
            )
        )

        filter_graph = (
            f"sendcmd="
            f"f='{safe_cmd_path}',"
            f"crop@smart="
            f"w={crop_width}:"
            f"h={height}:"
            f"x={initial_x}:"
            f"y=0,"
            f"scale="
            f"{TARGET_WIDTH}:"
            f"{TARGET_HEIGHT},"
            "setsar=1"
        )

        command = [

            "ffmpeg",

            "-y",

            "-loglevel",
            "error",

            "-i",
            video,

            "-vf",
            filter_graph,

            "-c:v",
            "libx264",

            "-preset",
            "fast",

            "-crf",
            "19",

            "-pix_fmt",
            "yuv420p",

            "-c:a",
            "copy",

            "-movflags",
            "+faststart",

            temp_output
        ]

        subprocess.run(
            command,
            check=True,
            timeout=900
        )

        os.replace(
            temp_output,
            video
        )

        print(
            "Smart reframe "
            "complete."
        )

        return True

    finally:

        import shutil

        shutil.rmtree(
            workdir,
            ignore_errors=True
        )


def main():

    videos = sorted(
        glob.glob(
            os.path.join(
                INPUT_DIR,
                "short_*.mp4"
            )
        )
    )

    if not videos:

        raise RuntimeError(
            "No Shorts found "
            "in output/"
        )

    changed = 0

    for video in videos:

        try:

            if reframe(video):

                changed += 1

        except Exception as error:

            print(
                "WARNING: smart "
                f"reframe failed for "
                f"{video}: "
                f"{type(error).__name__}: "
                f"{error}"
            )

            print(
                "Keeping existing "
                "rendered Short."
            )

    print(
        "=" * 50
    )

    print(
        "SMART REFRAME COMPLETE"
    )

    print(
        f"Videos found: "
        f"{len(videos)}"
    )

    print(
        f"Videos reframed: "
        f"{changed}"
    )

    print(
        "=" * 50
    )


if __name__ == "__main__":
    main()
