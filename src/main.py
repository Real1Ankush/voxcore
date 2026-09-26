import torch

from download import download_audio
from convert import convert_to_wav
from normalize import normalize_audio
from vad import remove_silence_vad
from transcribe import transcribe_audio
from summarizer import summarize_video


def preprocess_audio(youtube_url):
    print("=" * 60)
    print("Downloading audio...")
    audio_file, metadata = download_audio(youtube_url)

    print("Converting to WAV...")
    wav_file = convert_to_wav(audio_file)

    print("Normalizing audio...")
    normalized_audio = normalize_audio(wav_file)

    print("Removing silence...")
    clean_audio, timestamps = remove_silence_vad(
        normalized_audio
    )

    print("=" * 60)
    print("Audio preprocessing completed!")
    print("=" * 60)

    return {
        "title": metadata["title"],
        "duration": metadata["duration"],
        "clean_audio": clean_audio,
        "timestamps": timestamps,
        "metadata": metadata,
    }


def main():
    youtube_url = input("Enter The Youtube URL:")

    device = (
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    print(
        "CUDA Available:",
        torch.cuda.is_available()
    )

    if device == "cuda":
        print(
            "GPU:",
            torch.cuda.get_device_name(0)
        )
    else:
        print("Running on CPU")

    # --------------------------------------------------
    # 1. Download + preprocess audio
    # --------------------------------------------------

    result = preprocess_audio(youtube_url)

    print("\nTitle:", result["title"])

    print(
        "Duration:",
        result["duration"],
        "seconds"
    )

    print(
        "Clean Audio Path:",
        result["clean_audio"]
    )

    print(
        "VAD Segments:",
        len(result["timestamps"])
    )

    # --------------------------------------------------
    # 2. Transcription
    # --------------------------------------------------

    transcript, segments = transcribe_audio(
        result["clean_audio"],
        language="en",
        device=device,
        speech_timestamps=result["timestamps"],
    )

    # --------------------------------------------------
    # 3. Video summarization
    # --------------------------------------------------

    print("\n" + "=" * 60)
    print("Generating video summary...")
    print("=" * 60)

    summary = summarize_video(
        "downloads/transcript/transcript.json"
    )

    # --------------------------------------------------
    # 4. Completed
    # --------------------------------------------------

    print("\n" + "=" * 60)
    print("COMPLETE VIDEO PIPELINE FINISHED")
    print("=" * 60)

    print(
        "\nSummary file:"
        " downloads/transcript/video_summary.json"
    )


if __name__ == "__main__":
    main()