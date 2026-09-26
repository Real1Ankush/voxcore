"""
app.py -- VoxCore Flask web server

Routes:
    GET  /                 -- serve the web app
    POST /process          -- start video processing
    GET  /stream/<id>      -- Server-Sent Events for live progress
    POST /chat             -- RAG + LLM question answering
"""

import sys
import os
import uuid
import json
import queue
import threading
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    Response,
    stream_with_context,
)

from dotenv import load_dotenv


# ============================================================
# Make src/ importable
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"

sys.path.insert(0, str(SRC_DIR))


# ============================================================
# Import pipeline modules
# ============================================================

from download import download_audio
from convert import convert_to_wav
from normalize import normalize_audio
from vad import remove_silence_vad
from transcribe import transcribe_audio
from summarizer import summarize_video

from llm import (
    load_embed_model,
    load_transcript,
    chunk_documents,
    build_index,
    build_retriever,
    retrieve_chunks,
    build_prompt,
    call_llm,
)


# ============================================================
# Flask
# ============================================================

load_dotenv()

app = Flask(__name__)


# ============================================================
# In-memory job store
#
# job_id ->
# {
#     queue,
#     retriever,
#     title,
#     duration,
#     thumbnail,
#     transcript_preview,
#     chunk_count,
#     summary,
#     youtube_url
# }
# ============================================================

jobs = {}


# ============================================================
# Pipeline runner
# ============================================================

def run_pipeline(job_id: str, youtube_url: str) -> None:
    """
    Execute the complete video processing pipeline
    in a background thread.

    Pipeline:

        YouTube
           ↓
        Download
           ↓
        Convert
           ↓
        Normalize
           ↓
        VAD
           ↓
        Whisper
           ↓
        RAG Index
           ↓
        LLM Summary
    """

    q = jobs[job_id]["queue"]

    def emit(event: str, data: dict) -> None:
        """
        Push an SSE event into the job queue.
        """
        q.put({
            "event": event,
            "data": data,
        })

    try:

        # ====================================================
        # Device
        # ====================================================

        import torch

        device = (
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )

        # ====================================================
        # STEP 1 -- Download
        # ====================================================

        emit(
            "step",
            {
                "step": 1,
                "status": "running",
                "message": "Downloading audio from YouTube...",
            },
        )

        audio_file, metadata = download_audio(
            youtube_url
        )

        emit(
            "step",
            {
                "step": 1,
                "status": "done",
                "message": (
                    f"Downloaded: "
                    f"{metadata['title']}"
                ),
            },
        )

        # ====================================================
        # STEP 2 -- Convert
        # ====================================================

        emit(
            "step",
            {
                "step": 2,
                "status": "running",
                "message": (
                    "Converting to "
                    "16 kHz mono WAV..."
                ),
            },
        )

        wav_file = convert_to_wav(
            audio_file
        )

        emit(
            "step",
            {
                "step": 2,
                "status": "done",
                "message": (
                    "Converted to WAV successfully"
                ),
            },
        )

        # ====================================================
        # STEP 3 -- Normalize
        # ====================================================

        emit(
            "step",
            {
                "step": 3,
                "status": "running",
                "message": (
                    "Normalizing audio levels "
                    "(EBU R128)..."
                ),
            },
        )

        normalized = normalize_audio(
            wav_file
        )

        emit(
            "step",
            {
                "step": 3,
                "status": "done",
                "message": "Audio normalized",
            },
        )

        # ====================================================
        # STEP 4 -- VAD
        # ====================================================

        emit(
            "step",
            {
                "step": 4,
                "status": "running",
                "message": (
                    "Removing silence "
                    "with Silero VAD..."
                ),
            },
        )

        clean_audio, vad_timestamps = (
            remove_silence_vad(
                normalized
            )
        )

        emit(
            "step",
            {
                "step": 4,
                "status": "done",
                "message": "Silence removed",
            },
        )

        # ====================================================
        # STEP 5 -- Whisper transcription
        # ====================================================

        emit(
            "step",
            {
                "step": 5,
                "status": "running",
                "message": (
                    "Transcribing with "
                    f"Faster-Whisper "
                    f"({device.upper()})..."
                ),
            },
        )

        transcript_text, transcript_segments = (
            transcribe_audio(
                clean_audio,
                device=device,
                speech_timestamps=vad_timestamps,
            )
        )

        emit(
            "step",
            {
                "step": 5,
                "status": "done",
                "message": (
                    "Transcript ready"
                ),
            },
        )

        # ====================================================
        # STEP 6 -- RAG index
        # ====================================================

        emit(
            "step",
            {
                "step": 6,
                "status": "running",
                "message": (
                    "Embedding chunks & "
                    "building FAISS index..."
                ),
            },
        )

        transcript_path = (
            BASE_DIR
            / "downloads"
            / "transcript"
            / "transcript.txt"
        )

        load_embed_model()

        documents = load_transcript(
            transcript_path
        )

        nodes = chunk_documents(
            documents
        )

        index = build_index(
            nodes
        )

        retriever = build_retriever(
            index
        )

        emit(
            "step",
            {
                "step": 6,
                "status": "done",
                "message": (
                    f"Indexed {len(nodes)} "
                    "chunks — ready to chat!"
                ),
            },
        )

        # ====================================================
        # STEP 7 -- LLM video summary
        # ====================================================

        emit(
            "step",
            {
                "step": 7,
                "status": "running",
                "message": (
                    "Generating AI video summary..."
                ),
            },
        )

        transcript_json_path = (
            BASE_DIR
            / "downloads"
            / "transcript"
            / "transcript.json"
        )

        summary = summarize_video(
            transcript_json_path
        )

        summary_path = (
            BASE_DIR
            / "downloads"
            / "transcript"
            / "video_summary.json"
        )

        emit(
            "step",
            {
                "step": 7,
                "status": "done",
                "message": (
                    "AI video summary generated"
                ),
            },
        )

        # ====================================================
        # Store completed job
        # ====================================================

        jobs[job_id].update(
            {
                "retriever": retriever,

                "title": metadata.get(
                    "title",
                    "Unknown Title",
                ),

                "duration": metadata.get(
                    "duration",
                    0,
                ),

                "thumbnail": metadata.get(
                    "thumbnail",
                    "",
                ),

                "transcript_preview": (
                    transcript_text[:600]
                ),

                "chunk_count": len(nodes),

                "summary": summary,

                "summary_path": str(
                    summary_path
                ),

                "youtube_url": youtube_url,
            }
        )

        # ====================================================
        # Finished event
        # ====================================================

        emit(
            "done",
            {
                "title": metadata.get(
                    "title",
                    "Unknown Title",
                ),

                "duration": metadata.get(
                    "duration",
                    0,
                ),

                "thumbnail": metadata.get(
                    "thumbnail",
                    "",
                ),

                "transcript_preview": (
                    transcript_text[:600]
                ),

                "chunk_count": len(nodes),

                "summary": summary,

                "summary_path": str(
                    summary_path
                ),

                "youtube_url": youtube_url,
            },
        )

    except Exception as exc:

        # ====================================================
        # Error handling
        # ====================================================

        print(
            f"[ERROR] Job {job_id}: {exc}"
        )

        emit(
            "error",
            {
                "message": str(exc)
            },
        )

    finally:

        # ====================================================
        # SSE sentinel
        # ====================================================

        q.put(None)


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ============================================================
# START PROCESSING
# ============================================================

@app.route(
    "/process",
    methods=["POST"],
)
def process():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    youtube_url = (
        data.get("url", "")
        .strip()
    )

    if not youtube_url:

        return jsonify(
            {
                "error": (
                    "A YouTube URL is required."
                )
            }
        ), 400

    # Create job
    job_id = str(
        uuid.uuid4()
    )

    jobs[job_id] = {

        "queue": queue.Queue(),

        "retriever": None,

        "title": None,

        "duration": None,

        "thumbnail": None,

        "transcript_preview": None,

        "chunk_count": 0,

        "summary": None,

        "summary_path": None,

        "youtube_url": youtube_url,
    }

    # Start background pipeline
    thread = threading.Thread(
        target=run_pipeline,
        args=(
            job_id,
            youtube_url,
        ),
        daemon=True,
    )

    thread.start()

    return jsonify(
        {
            "job_id": job_id
        }
    )


# ============================================================
# SERVER-SENT EVENTS
# ============================================================

@app.route(
    "/stream/<job_id>"
)
def stream(job_id: str):

    if job_id not in jobs:

        return jsonify(
            {
                "error": "Job not found."
            }
        ), 404

    def generate():

        q = jobs[job_id]["queue"]

        while True:

            item = q.get()

            if item is None:
                break

            yield (
                f"event: {item['event']}\n"
                f"data: "
                f"{json.dumps(item['data'])}\n\n"
            )

    return Response(
        stream_with_context(
            generate()
        ),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ============================================================
# CHAT / RAG
# ============================================================

@app.route(
    "/chat",
    methods=["POST"],
)
def chat():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    job_id = (
        data.get("job_id", "")
        .strip()
    )

    query = (
        data.get("query", "")
        .strip()
    )

    if (
        not job_id
        or job_id not in jobs
    ):

        return jsonify(
            {
                "error": (
                    "Invalid or expired "
                    "job ID."
                )
            }
        ), 400

    if not query:

        return jsonify(
            {
                "error": (
                    "Query cannot be empty."
                )
            }
        ), 400

    retriever = (
        jobs[job_id]
        .get("retriever")
    )

    if not retriever:

        return jsonify(
            {
                "error": (
                    "Pipeline is still "
                    "running. Please wait."
                )
            }
        ), 400

    hf_token = os.environ.get(
        "HF_TOKEN"
    )

    retrieved_nodes = (
        retrieve_chunks(
            retriever,
            query,
        )
    )

    prompt = build_prompt(
        query,
        retrieved_nodes,
    )

    answer = call_llm(
        prompt,
        hf_token=hf_token,
    )

    return jsonify(
        {
            "answer": answer,
            "chunks_used": len(
                retrieved_nodes
            ),
        }
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True,
        port=5000,
        threaded=True,
    )