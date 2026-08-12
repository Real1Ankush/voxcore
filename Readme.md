# 🎙️VoxCore: Audio-RAG-Summarizer

> **End-to-end pipeline that transcribes audio, builds a RAG index, and generates intelligent summaries using Llama..**

## 🛠️ Tech Stack 

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge\&logo=python\&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge\&logo=fastapi\&logoColor=white)
![LlamaIndex](https://img.shields.io/badge/LlamaIndex-6E57E0?style=for-the-badge)
![FAISS](https://img.shields.io/badge/FAISS-0467DF?style=for-the-badge)
![Faster Whisper](https://img.shields.io/badge/Faster--Whisper-FF6F00?style=for-the-badge)
![Hugging Face](https://img.shields.io/badge/Hugging%20Face-FFD21E?style=for-the-badge\&logo=huggingface\&logoColor=black)
![BGE Embeddings](https://img.shields.io/badge/BGE%20Embeddings-4CAF50?style=for-the-badge)
![Llama](https://img.shields.io/badge/Llama-7B42BC?style=for-the-badge\&logo=meta\&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-007808?style=for-the-badge\&logo=ffmpeg\&logoColor=white)

---

## 🏗️ Architecture

```text
Audio File
   │
   ▼
Audio Pre-processing  (src/audio.py)
   │  – resample → 16 kHz mono WAV
   ▼
Faster-Whisper        (src/transcriber.py)
   │  – word-level timestamps, language detection
   ▼
Transcript Loader     (src/loader.py)
   │  – loads .txt / .json transcript
   ▼
Sentence Chunker      (src/chunker.py)
   │  – SentenceSplitter, configurable chunk/overlap size
   ▼
BGE Embedder          (src/embedder.py)
   │  – BAAI/bge-small-en-v1.5 (local)
   ▼
Vector Store          (src/vector_store.py)
   │  – LlamaIndex + FAISS index, persisted to data/index/
   ▼
Dense Retriever       (src/retriever.py)
   │  – top-k similarity search
   ▼
Prompt Builder        (src/prompt.py)
   │  – zero-shot summarization prompt
   ▼
Llama LLM             (src/llm.py)
   │  – OpenAI-compatible Llama API
   ▼
Summarizer            (src/summarizer.py)
   │  – orchestrates retrieval + generation
   ▼
Output                (outputs/summaries/)
```
