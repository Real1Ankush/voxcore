import torch
import soundfile as sf
from pathlib import Path

from silero_vad import (
    load_silero_vad,
    get_speech_timestamps,
    collect_chunks,
)


def remove_silence_vad(input_audio):
    input_audio = Path(input_audio)

    output_audio = input_audio.with_name(
        input_audio.stem + "_speech.wav"
    )

    audio, sample_rate = sf.read(
        str(input_audio),
        dtype="float32",
    )

    if sample_rate != 16000:
        raise ValueError(
            f"Expected 16000 Hz audio, but received {sample_rate} Hz."
        )

    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    wav = torch.from_numpy(audio)

    model = load_silero_vad()

    speech_timestamps = get_speech_timestamps(
        wav,
        model,
        sampling_rate=16000,
        threshold=0.5,
        min_speech_duration_ms=250,
        min_silence_duration_ms=500,
        speech_pad_ms=200,
    )

    speech = collect_chunks(
        speech_timestamps,
        wav,
    )

    sf.write(
        str(output_audio),
        speech.numpy(),
        16000,
        subtype="PCM_16",
    )

    return output_audio, speech_timestamps


def timestamps_to_seconds(
    timestamps,
    sample_rate=16000,
):
    return [
        {
            "start": round(
                t["start"] / sample_rate,
                2,
            ),
            "end": round(
                t["end"] / sample_rate,
                2,
            ),
        }
        for t in timestamps
    ]