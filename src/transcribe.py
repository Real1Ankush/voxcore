import os
import torch

# ---------------------------------------------------------------------------
# Fix CUDA DLL discovery for Faster-Whisper / CTranslate2 on Windows
# ---------------------------------------------------------------------------

torch_lib = os.path.join(
    os.path.dirname(torch.__file__),
    "lib"
)

os.add_dll_directory(torch_lib)

import json
from pathlib import Path

from faster_whisper import WhisperModel


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "large-v3"


# ---------------------------------------------------------------------------
# Map Whisper timestamps back to original audio timestamps
# ---------------------------------------------------------------------------

def map_to_original_timestamps(
    start,
    end,
    speech_timestamps,
    sample_rate=16000,
):
    """
    Map timestamps from the VAD-compressed speech-only audio
    back to the original audio timeline.

    Whisper timestamps refer to the speech-only audio because
    silence was removed before transcription.
    """

    if not speech_timestamps:
        return start, end

    accumulated_speech = 0.0

    mapped_start = None
    mapped_end = None

    for timestamp in speech_timestamps:

        original_start = (
            timestamp["start"] / sample_rate
        )

        original_end = (
            timestamp["end"] / sample_rate
        )

        chunk_duration = (
            original_end - original_start
        )

        speech_chunk_start = accumulated_speech

        speech_chunk_end = (
            accumulated_speech + chunk_duration
        )

        # -------------------------------------------------
        # Does Whisper START fall inside this VAD chunk?
        # -------------------------------------------------

        if (
            mapped_start is None
            and start >= speech_chunk_start
            and start <= speech_chunk_end
        ):

            local_start = (
                start - speech_chunk_start
            )

            mapped_start = (
                original_start + local_start
            )

        # -------------------------------------------------
        # Does Whisper END fall inside this VAD chunk?
        # -------------------------------------------------

        if (
            end >= speech_chunk_start
            and end <= speech_chunk_end
        ):

            local_end = (
                end - speech_chunk_start
            )

            mapped_end = (
                original_start + local_end
            )

            break

        accumulated_speech += chunk_duration

    # -----------------------------------------------------
    # Fallback protection
    # -----------------------------------------------------

    if mapped_start is None:
        mapped_start = start

    if mapped_end is None:
        mapped_end = end

    return mapped_start, mapped_end

# ---------------------------------------------------------------------------
# Main transcription function
# ---------------------------------------------------------------------------

def transcribe_audio(
    audio_path,
    output_dir="downloads/transcript",
    language=None,
    device="cuda",
    model_name=DEFAULT_MODEL,
    speech_timestamps=None,
):
    """
    Transcribe an audio file using Faster-Whisper.

    Outputs
    -------
    transcript.txt
        Plain-text transcript.

    transcript.json
        Structured timestamp-preserving transcript.

    Parameters
    ----------
    audio_path : str or Path
        Path to the speech-only WAV file.

    output_dir : str or Path
        Directory where transcript files are saved.

    language : str or None
        Language passed to Faster-Whisper.

    device : str
        "cuda" or "cpu".

    model_name : str
        Faster-Whisper model name.

    speech_timestamps : list or None
        Original Silero VAD timestamps.

    Returns
    -------
    tuple
        transcript_text, segments_data
    """

    audio_path = Path(audio_path)
    output_dir = Path(output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -----------------------------------------------------------------------
    # Select compute type
    # -----------------------------------------------------------------------

    if device == "cuda":
        compute_type = "float16"
    else:
        compute_type = "int8"

    print("=" * 70)
    print("TRANSCRIPTION")
    print("=" * 70)

    print(f"Model       : {model_name}")
    print(f"Device      : {device}")
    print(f"Compute     : {compute_type}")
    print(f"Audio       : {audio_path}")

    if speech_timestamps:
        print(
            f"VAD segments: {len(speech_timestamps)}"
        )

    # -----------------------------------------------------------------------
    # Load Whisper model
    # -----------------------------------------------------------------------

    model = WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
    )

    # -----------------------------------------------------------------------
    # Transcribe
    # -----------------------------------------------------------------------

    segments, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        vad_filter=False,
        language=language,
    )

    transcript = []
    segments_data = []

    print("-" * 70)

    # -----------------------------------------------------------------------
    # Process Whisper segments
    # -----------------------------------------------------------------------

    for index, segment in enumerate(segments):

        text = segment.text.strip()

        if not text:
            continue

        # Whisper timestamps are relative to the speech-only audio
        whisper_start = float(segment.start)
        whisper_end = float(segment.end)

        # ---------------------------------------------------------------
        # Convert speech-only timestamps back to original timestamps
        # ---------------------------------------------------------------

        start, end = map_to_original_timestamps(
            whisper_start,
            whisper_end,
            speech_timestamps,
        )

        start = round(start, 2)
        end = round(end, 2)

        transcript.append(text)

        segments_data.append(
            {
                "id": index,
                "start": start,
                "end": end,
                "text": text,
            }
        )

        print(
            f"[{start:>8.2f}s → {end:>8.2f}s] {text}"
        )

    # -----------------------------------------------------------------------
    # Build plain-text transcript
    # -----------------------------------------------------------------------

    transcript_text = "\n".join(
        transcript
    )

    txt_file = (
        output_dir / "transcript.txt"
    )

    with open(
        txt_file,
        "w",
        encoding="utf-8",
    ) as f:
        f.write(transcript_text)

    # -----------------------------------------------------------------------
    # Build structured transcript
    # -----------------------------------------------------------------------

    transcript_data = {
        "language": info.language,
        "language_probability": round(
            float(info.language_probability),
            4,
        ),
        "duration": round(
            float(info.duration),
            2,
        ),
        "model": model_name,
        "segments": segments_data,
    }

    json_file = (
        output_dir / "transcript.json"
    )

    with open(
        json_file,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            transcript_data,
            f,
            indent=2,
            ensure_ascii=False,
        )

    # -----------------------------------------------------------------------
    # Final information
    # -----------------------------------------------------------------------

    print("=" * 70)
    print("TRANSCRIPTION COMPLETED")
    print("=" * 70)

    print(
        f"Language              : {info.language}"
    )

    print(
        f"Language probability  : "
        f"{info.language_probability:.4f}"
    )

    print(
        f"Duration              : "
        f"{info.duration:.2f} seconds"
    )

    print(
        f"Segments              : "
        f"{len(segments_data)}"
    )

    print(
        f"Text transcript       : "
        f"{txt_file}"
    )

    print(
        f"Structured transcript : "
        f"{json_file}"
    )

    return transcript_text, segments_data