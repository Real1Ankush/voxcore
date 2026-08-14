"""
app.py  --  VoxCore Flask web server
Exposes the full pipeline via three routes:
  GET  /               -- serve the SPA
  POST /process        -- start pipeline, return job_id
  GET  /stream/<id>    -- Server-Sent Events for live progress
  POST /chat           -- RAG + LLM query against processed video
"""

import sys
import os
import uuid
import json
import queue
import threading
from pathlib import Path

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv

# ── Make src/ importable ──────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent / "src"))

from download import download_audio
from convert import convert_to_wav
from normalize import normalize_audio
from vad import remove_silence_vad
from transcribe import transcribe_audio
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

load_dotenv()
app = Flask(__name__)

# ── In-memory job store ───────────────────────────────────────────────────────
# job_id -> { queue, retriever, title, duration, thumbnail,
#             transcript_preview, chunk_count }
jobs: dict = {}


# ── Pipeline runner (background thread) ──────────────────────────────────────

def run_pipeline(job_id: str, youtube_url: str) -> None:
    """Execute every stage of the pipeline and push SSE events onto the queue."""
    q: queue.Queue = jobs[job_id]["queue"]

    def emit(event: str, data: dict) -> None:
        q.put({"event": event, "data": data})

    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"

        # ── Step 1: Download ──────────────────────────────────────────────────
        emit("step", {"step": 1, "status": "running", "message": "Downloading audio from YouTube..."})
        audio_file, metadata = download_audio(youtube_url)
        emit("step", {"step": 1, "status": "done", "message": f"Downloaded: {metadata['title']}"})

        # ── Step 2: Convert ───────────────────────────────────────────────────
        emit("step", {"step": 2, "status": "running", "message": "Converting to 16 kHz mono WAV..."})
        wav_file = convert_to_wav(audio_file)
        emit("step", {"step": 2, "status": "done", "message": "Converted to WAV successfully"})

        # ── Step 3: Normalize ─────────────────────────────────────────────────
        emit("step", {"step": 3, "status": "running", "message": "Normalizing audio levels (EBU R128)..."})
        normalized = normalize_audio(wav_file)
        emit("step", {"step": 3, "status": "done", "message": "Audio normalized"})

        # ── Step 4: VAD ───────────────────────────────────────────────────────
        emit("step", {"step": 4, "status": "running", "message": "Removing silence with Silero VAD..."})
        clean_audio, _ = remove_silence_vad(normalized)
        emit("step", {"step": 4, "status": "done", "message": "Silence removed"})

        # ── Step 5: Transcribe ────────────────────────────────────────────────
        emit("step", {"step": 5, "status": "running",
                      "message": f"Transcribing with Faster-Whisper ({device.upper()})..."})
        transcript_text, _ = transcribe_audio(clean_audio, device=device)
        emit("step", {"step": 5, "status": "done", "message": "Transcript ready"})

        # ── Step 6: Build RAG Index ───────────────────────────────────────────
        emit("step", {"step": 6, "status": "running", "message": "Embedding chunks & building FAISS index..."})
        transcript_path = Path("downloads/transcript/transcript.txt")
        load_embed_model()
        documents = load_transcript(transcript_path)
        nodes = chunk_documents(documents)
        index = build_index(nodes)
        retriever = build_retriever(index)
        emit("step", {"step": 6, "status": "done", "message": f"Indexed {len(nodes)} chunks — ready to chat!"})

        # ── Store results ─────────────────────────────────────────────────────
        jobs[job_id].update({
            "retriever": retriever,
            "title": metadata["title"],
            "duration": metadata.get("duration", 0),
            "thumbnail": metadata.get("thumbnail", ""),
            "transcript_preview": transcript_text[:600],
            "chunk_count": len(nodes),
        })

        emit("done", {
            "title": metadata["title"],
            "duration": metadata.get("duration", 0),
            "thumbnail": metadata.get("thumbnail", ""),
            "transcript_preview": transcript_text[:600],
            "chunk_count": len(nodes),
        })

    except Exception as exc:
        emit("error", {"message": str(exc)})
    finally:
        q.put(None)  # sentinel — tells the SSE generator to close


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json(silent=True) or {}
    youtube_url = data.get("url", "").strip()
    if not youtube_url:
        return jsonify({"error": "A YouTube URL is required."}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "queue": queue.Queue(),
        "retriever": None,
        "title": None,
        "duration": None,
        "thumbnail": None,
        "transcript_preview": None,
        "chunk_count": 0,
    }

    t = threading.Thread(target=run_pipeline, args=(job_id, youtube_url), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id: str):
    if job_id not in jobs:
        return jsonify({"error": "Job not found."}), 404

    def generate():
        q = jobs[job_id]["queue"]
        while True:
            item = q.get()
            if item is None:
                break
            yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id", "").strip()
    query = data.get("query", "").strip()

    if not job_id or job_id not in jobs:
        return jsonify({"error": "Invalid or expired job ID."}), 400
    if not query:
        return jsonify({"error": "Query cannot be empty."}), 400

    retriever = jobs[job_id].get("retriever")
    if not retriever:
        return jsonify({"error": "Pipeline is still running. Please wait."}), 400

    hf_token = os.environ.get("HF_TOKEN")
    retrieved_nodes = retrieve_chunks(retriever, query)
    prompt = build_prompt(query, retrieved_nodes)
    answer = call_llm(prompt, hf_token=hf_token)

    return jsonify({"answer": answer, "chunks_used": len(retrieved_nodes)})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
