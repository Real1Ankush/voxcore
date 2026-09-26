# VoxCore

VoxCore is an AI-powered video understanding pipeline that converts YouTube video audio into a timestamped transcript, generates an educational summary, and provides a retrieval-based chat interface for asking questions about the processed video.

## Before vs After

### Before: original pipeline

```text
YouTube URL
    ↓
Download Audio
    ↓
Convert to WAV
    ↓
Transcribe Audio
    ↓
Transcript
    ↓
Chunk Transcript
    ↓
Embeddings / Vector Index
    ↓
Retriever
    ↓
LLM
    ↓
Question Answering / Chat
```

The original project was mainly focused on transcription, retrieval and question answering.

### After: improved pipeline

```text
YouTube Video
    ↓
Download Audio
    ↓
Convert to WAV
    ↓
Normalize Audio
    ↓
Silero VAD / Remove Silence
    ↓
Faster-Whisper large-v3
    ↓
Restore Original Video Timestamps
    │
    ├──────────────→ RAG / Chat
    │
    └──────────────→ Chronological Transcript Chunks
                            ↓
                     Section LLM Summaries
                            ↓
                     Final LLM Summary
                            ↓
                  Timestamped Structured JSON
                            ↓
                     Flask Web Interface
```

## What Changed

### 1. Audio normalization

Audio is now normalized before VAD and transcription using FFmpeg loudness normalization. This gives the speech-processing stages a more consistent audio signal.

### 2. Silero VAD

A Voice Activity Detection stage was added.

```text
Normalized Audio → Silero VAD → Speech-only Audio
```

Silent regions are removed before transcription, while the original speech-region timestamps are retained.

### 3. Original timestamp restoration

Removing silence compresses the audio timeline. Whisper timestamps therefore refer to the compressed speech-only audio.

VoxCore now maps those timestamps back to the original video timeline:

```text
Whisper timestamp
      ↓
VAD speech segments
      ↓
Original video timestamp
```

This allows summaries to reference the actual video timeline.

### 4. Improved transcription pipeline

VoxCore uses Faster-Whisper with automatic CUDA/CPU selection.

```text
CUDA available    → GPU + float16
CUDA unavailable  → CPU + int8
```

The transcript is stored with structured timestamps:

```json
{
  "start": 12.42,
  "end": 16.81,
  "text": "..."
}
```

### 5. Added dedicated full-video summarization

A new `src/summarizer.py` module was added.

The RAG/chat system and full-video summarizer are separate:

```text
RAG / Chat:
Question → Retrieve relevant chunks → LLM → Answer

Summarizer:
Entire transcript → Chronological chunks
→ Section summaries → Final LLM summary
```

### 6. Chronological transcript chunking

The transcript is divided into chronological sections while preserving the original timestamps.

```json
{
  "start": 120.5,
  "end": 168.2,
  "text": "..."
}
```

### 7. Hierarchical LLM summarization

Each transcript chunk is summarized first:

```text
Chunk 1 → Summary 1
Chunk 2 → Summary 2
Chunk 3 → Summary 3
...
```

The section summaries are then combined by the LLM into the final video summary.

### 8. Structured JSON summary

The final output contains:

```json
{
  "overview": "...",
  "key_points": ["...", "..."],
  "topics": [
    {
      "title": "...",
      "start": 120.5,
      "end": 180.2,
      "summary": "..."
    }
  ],
  "takeaways": ["...", "..."]
}
```

The timestamped `topics` make it possible for the frontend to associate summary sections with locations in the video.

### 9. Flask web pipeline integration

The web application now exposes seven processing stages:

```text
Step 1  Download audio
Step 2  Convert to WAV
Step 3  Normalize audio
Step 4  Remove silence
Step 5  Transcribe
Step 6  Build retrieval index
Step 7  Generate AI summary
```

Progress is streamed to the frontend using Server-Sent Events (SSE).

### 10. Generated summary artifacts

The summarization pipeline produces:

```text
downloads/transcript/
├── transcript.json
├── transcript.txt
├── chunk_summaries.json
└── video_summary.json
```

These generated files are excluded from GitHub with `.gitignore`.

## RAG vs Summarization

### `src/llm.py`

Responsible for:

- transcript loading
- embeddings
- retrieval chunking
- vector index creation
- retrieval
- question-answering prompts
- chat responses

### `src/summarizer.py`

Responsible for:

- timestamped transcript loading
- chronological summarization chunks
- section summaries
- final video summary
- timestamped topics
- structured JSON output

Keeping these workflows separate allows VoxCore to support both video summarization and question answering.

## Project Structure

```text
VoxCore/
├── .dockerignore
├── .gitignore
├── Dockerfile
├── README.md
├── app.py
├── requirements.txt
│
├── src/
│   ├── convert.py
│   ├── download.py
│   ├── llm.py
│   ├── normalize.py
│   ├── summarizer.py
│   ├── test_summarizer.py
│   ├── transcribe.py
│   └── vad.py
│
├── static/
│   ├── app.js
│   └── style.css
│
└── templates/
    └── index.html
```

## Main Components

| Component | Purpose |
|---|---|
| `download.py` | Downloads YouTube audio |
| `convert.py` | Converts audio to mono 16 kHz WAV |
| `normalize.py` | Normalizes audio loudness |
| `vad.py` | Detects speech and removes silence |
| `transcribe.py` | Generates timestamped transcription |
| `summarizer.py` | Generates hierarchical video summaries |
| `llm.py` | Handles embeddings, retrieval and chat |
| `app.py` | Flask backend and web pipeline |
| `static/app.js` | Frontend interaction and pipeline updates |
| `static/style.css` | Web interface styling |
| `templates/index.html` | Web interface |

## Setup

### 1. Clone

```bash
git clone https://github.com/Real1Ankush/voxcore.git
cd voxcore
```

### 2. Create a virtual environment

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure Hugging Face

The LLM calls require a Hugging Face API token.

PowerShell:

```powershell
$env:HF_TOKEN="your_huggingface_token"
```

Or create a local `.env` file:

```env
HF_TOKEN=your_huggingface_token
```

Do not commit `.env` to GitHub.

## Running VoxCore

Start the Flask application:

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

You can also run the core pipeline directly:

```powershell
python src/main.py
```

## Output

After processing a video:

```text
downloads/transcript/
├── transcript.txt
├── transcript.json
├── chunk_summaries.json
└── video_summary.json
```

## Technology Stack

- Python
- Flask
- FFmpeg
- yt-dlp
- Silero VAD
- Faster-Whisper
- PyTorch
- LlamaIndex
- Hugging Face
- Llama 3.1 8B Instruct
- HTML / CSS / JavaScript
- Server-Sent Events (SSE)

## GitHub Notes

The following local/generated content should not be committed:

```text
.venv/
downloads/
.env
__pycache__/
```

These are excluded through `.gitignore`.

## Upgrade Summary

### Before

```text
YouTube
  ↓
Audio
  ↓
Transcript
  ↓
Embeddings
  ↓
Retriever
  ↓
LLM
  ↓
Chat
```

### After

```text
YouTube
  ↓
Audio Download
  ↓
WAV Conversion
  ↓
Normalization
  ↓
Silero VAD
  ↓
Faster-Whisper
  ↓
Original Timestamp Restoration
  │
  ├──────────────→ RAG / Chat
  │
  └──────────────→ Chunking
                       ↓
                 Section Summaries
                       ↓
                 Final LLM Summary
                       ↓
                 Timestamped Topics
                       ↓
                 Web Interface
```

The main architectural change is that VoxCore evolved from a transcription + retrieval/chat pipeline into a video understanding pipeline supporting both retrieval-based interaction and structured full-video summarization.
