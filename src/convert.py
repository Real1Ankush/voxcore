import ffmpeg
from pathlib import Path


def convert_to_wav(input_file, output_dir="downloads"):
    input_file = Path(input_file)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{input_file.stem}.wav"

    # If the WAV already exists, reuse it.
    if output_file.exists():
        print(f"WAV already exists: {output_file}")
        return output_file

    (
        ffmpeg
        .input(str(input_file))
        .output(
            str(output_file),
            ac=1,
            ar=16000,
            acodec="pcm_s16le",
            format="wav",
        )
        .overwrite_output()
        .run()
    )

    return output_file