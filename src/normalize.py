import ffmpeg
from pathlib import Path


def normalize_audio(input_audio):
    input_audio = Path(input_audio)

    output_audio = input_audio.with_name(
        input_audio.stem + "_normalized.wav"
    )

    (
        ffmpeg
        .input(str(input_audio))
        .output(
            str(output_audio),
            af="loudnorm=I=-16:LRA=11:TP=-1.5",
            ac=1,
            ar=16000,
            acodec="pcm_s16le",
            format="wav",
        )
        .overwrite_output()
        .run()
    )

    return output_audio