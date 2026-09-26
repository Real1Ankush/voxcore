import json
import os
from pathlib import Path

from huggingface_hub import InferenceClient


MODEL_NAME = "meta-llama/Llama-3.1-8B-Instruct"
TEMPERATURE = 0.2
MAX_TOKENS = 700


def load_transcript(transcript_path):
    transcript_path = Path(transcript_path)

    with open(transcript_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


def create_chunks(segments, max_chars=3000):
    """
    Create chronological transcript chunks while preserving
    original video timestamps.
    """

    chunks = []
    current_segments = []
    current_chars = 0

    for segment in segments:
        text = segment["text"].strip()

        if not text:
            continue

        text_length = len(text)

        if (
            current_segments
            and current_chars + text_length > max_chars
        ):
            chunks.append({
                "start": current_segments[0]["start"],
                "end": current_segments[-1]["end"],
                "text": " ".join(
                    s["text"] for s in current_segments
                ),
            })

            current_segments = []
            current_chars = 0

        current_segments.append(segment)
        current_chars += text_length

    if current_segments:
        chunks.append({
            "start": current_segments[0]["start"],
            "end": current_segments[-1]["end"],
            "text": " ".join(
                s["text"] for s in current_segments
            ),
        })

    return chunks


def call_llm(
    prompt,
    hf_token=None,
    model=MODEL_NAME,
    temperature=TEMPERATURE,
    max_tokens=MAX_TOKENS,
):
    token = hf_token or os.environ.get("HF_TOKEN")

    if not token:
        raise ValueError(
            "HF_TOKEN is not set. "
            "Set your Hugging Face token before running."
        )

    client = InferenceClient(api_key=token)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        },
    )

    return response.choices[0].message.content.strip()


def summarize_chunk(chunk, hf_token=None):
    prompt = f"""
You are an educational video summarization assistant.

Summarize ONLY the information contained in the transcript below.

Do not invent facts.
Do not add information that is not present.
Preserve important technical terms, facts, examples, and explanations.

VIDEO TIMESTAMP:
{chunk["start"]:.2f} - {chunk["end"]:.2f} seconds

TRANSCRIPT:
{chunk["text"]}

Write a concise summary of this section in 2-4 sentences.
"""

    return call_llm(
        prompt,
        hf_token=hf_token,
        max_tokens=300,
    )


def generate_final_summary(
    chunks,
    chunk_summaries,
    hf_token=None,
):
    """
    Generate the final structured video summary.
    """

    context = []

    for chunk, summary in zip(chunks, chunk_summaries):
        context.append({
            "start": round(chunk["start"], 2),
            "end": round(chunk["end"], 2),
            "summary": summary,
        })

    context_text = json.dumps(
        context,
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"""
You are an educational video summarization assistant.

Create a structured summary of the entire video using ONLY
the section summaries provided below.

Do not invent information.

Return ONLY valid JSON.
Do not use markdown.
Do not wrap the JSON in ```json or ```.

The JSON MUST have exactly this structure:

{{
  "overview": "string",
  "key_points": [
    "string"
  ],
  "topics": [
    {{
      "title": "string",
      "start": 0.0,
      "end": 0.0,
      "summary": "string"
    }}
  ],
  "takeaways": [
    "string"
  ]
}}

Rules:

1. Every topic MUST have numeric start and end timestamps.

2. Use the supplied section timestamps.

3. Topic timestamps must come from the supplied
   section timestamps.

4. Keep topics in chronological order.

5. Do not create topics for filler,
   introductions, advertisements, or transitions.

6. Do not write "not specified" for timestamps.

7. Use ONLY information contained in the
   section summaries.

8. Keep the overview concise.

9. Key points should contain the most important
   information from the entire video.

10. Takeaways should contain the main educational
    lessons from the video.

SECTION SUMMARIES:

{context_text}
"""

    raw = call_llm(
        prompt,
        hf_token=hf_token,
        max_tokens=1000,
    )

    raw = raw.strip()

    # Remove accidental markdown code fences
    if raw.startswith("```json"):
        raw = raw[7:].strip()

    elif raw.startswith("```"):
        raw = raw[3:].strip()

    if raw.endswith("```"):
        raw = raw[:-3].strip()

    try:
        result = json.loads(raw)

    except json.JSONDecodeError as exc:
        raise ValueError(
            "LLM did not return valid JSON.\n\n"
            f"Raw response:\n{raw}"
        ) from exc

    required_keys = {
        "overview",
        "key_points",
        "topics",
        "takeaways",
    }

    if set(result.keys()) != required_keys:
        raise ValueError(
            "Invalid summary structure.\n"
            f"Expected keys: {required_keys}\n"
            f"Received keys: {set(result.keys())}"
        )

    # Validate topics
    for topic in result["topics"]:

        if "title" not in topic:
            raise ValueError(
                f"Topic is missing 'title': {topic}"
            )

        if "start" not in topic:
            raise ValueError(
                f"Topic is missing 'start': {topic}"
            )

        if "end" not in topic:
            raise ValueError(
                f"Topic is missing 'end': {topic}"
            )

        if "summary" not in topic:
            raise ValueError(
                f"Topic is missing 'summary': {topic}"
            )

        if not isinstance(
            topic["start"],
            (int, float),
        ):
            raise ValueError(
                f"Invalid topic start timestamp: {topic}"
            )

        if not isinstance(
            topic["end"],
            (int, float),
        ):
            raise ValueError(
                f"Invalid topic end timestamp: {topic}"
            )

        if topic["start"] < 0:
            raise ValueError(
                f"Negative topic start timestamp: {topic}"
            )

        if topic["end"] <= topic["start"]:
            raise ValueError(
                f"Invalid topic time range: {topic}"
            )

    # Make sure topics are chronological
    result["topics"].sort(
        key=lambda topic: topic["start"]
    )

    return result


def summarize_video(
    transcript_path,
    output_dir=None,
    hf_token=None,
):
    transcript_path = Path(transcript_path)

    if output_dir is None:
        output_dir = transcript_path.parent

    output_dir = Path(output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 70)
    print("VIDEO SUMMARIZATION")
    print("=" * 70)

    # ---------------------------------------------------------
    # 1. Load timestamped transcript
    # ---------------------------------------------------------

    data = load_transcript(transcript_path)

    segments = data["segments"]

    print(
        f"Transcript segments: {len(segments)}"
    )

    # ---------------------------------------------------------
    # 2. Create chronological chunks
    # ---------------------------------------------------------

    chunks = create_chunks(segments)

    print(
        f"Summary chunks created: {len(chunks)}"
    )

    # ---------------------------------------------------------
    # 3. Summarize each chunk
    # ---------------------------------------------------------

    chunk_summaries = []

    for i, chunk in enumerate(
        chunks,
        start=1,
    ):

        print(
            f"\nSummarizing chunk {i}/{len(chunks)} "
            f"({chunk['start']:.2f}s → "
            f"{chunk['end']:.2f}s)"
        )

        summary = summarize_chunk(
            chunk,
            hf_token=hf_token,
        )

        chunk_summaries.append(summary)

        print(summary)

    # ---------------------------------------------------------
    # 4. Generate final structured summary
    # ---------------------------------------------------------

    print("\nGenerating final summary...")

    final_summary = generate_final_summary(
        chunks,
        chunk_summaries,
        hf_token=hf_token,
    )

    # ---------------------------------------------------------
    # 5. Save intermediate summaries
    # ---------------------------------------------------------

    chunk_file = (
        output_dir / "chunk_summaries.json"
    )

    chunk_data = []

    for chunk, summary in zip(
        chunks,
        chunk_summaries,
    ):
        chunk_data.append({
            "start": chunk["start"],
            "end": chunk["end"],
            "transcript": chunk["text"],
            "summary": summary,
        })

    with open(
        chunk_file,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            chunk_data,
            f,
            indent=2,
            ensure_ascii=False,
        )

    # ---------------------------------------------------------
    # 6. Save final structured summary
    # ---------------------------------------------------------

    summary_file = (
        output_dir / "video_summary.json"
    )

    with open(
        summary_file,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            final_summary,
            f,
            indent=2,
            ensure_ascii=False,
        )

    # ---------------------------------------------------------
    # 7. Display final summary
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("VIDEO SUMMARY")
    print("=" * 70)

    print(
        json.dumps(
            final_summary,
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\nSaved:")
    print(f"Chunk summaries : {chunk_file}")
    print(f"Final summary   : {summary_file}")

    return final_summary