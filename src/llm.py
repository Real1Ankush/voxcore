import os
from pathlib import Path

from llama_index.core import Settings, VectorStoreIndex, SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from huggingface_hub import InferenceClient


# -- Constants -----------------------------------------------------------------

EMBED_MODEL_NAME  = "BAAI/bge-base-en-v1.5"
LLM_MODEL_NAME    = "meta-llama/Llama-3.1-8B-Instruct"
CHUNK_SIZE        = 300
CHUNK_OVERLAP     = 50
SIMILARITY_TOP_K  = 10
LLM_TEMPERATURE   = 0.2
LLM_MAX_TOKENS    = 700


# -- Step 1: Load embedding model ----------------------------------------------

def load_embed_model(model_name: str = EMBED_MODEL_NAME) -> HuggingFaceEmbedding:
    """Load and register a HuggingFace embedding model with LlamaIndex Settings."""
    embed_model = HuggingFaceEmbedding(model_name=model_name)
    Settings.embed_model = embed_model
    return embed_model


# -- Step 2: Load transcript document ------------------------------------------

def load_transcript(transcript_path: str | Path):
    """
    Load a transcript text file as a list of LlamaIndex Document objects.

    Args:
        transcript_path: Absolute or relative path to the .txt transcript file.

    Returns:
        List of Document objects.
    """
    transcript_path = Path(transcript_path)

    documents = SimpleDirectoryReader(
        input_files=[str(transcript_path)]
    ).load_data()

    print(f"Loaded {len(documents)} document(s) from: {transcript_path}")
    return documents


# -- Step 3: Chunk documents into nodes ----------------------------------------

def chunk_documents(
    documents,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
):
    """
    Split documents into overlapping sentence-level chunks (nodes).

    Args:
        documents:     List of LlamaIndex Document objects.
        chunk_size:    Maximum tokens per chunk (default 300).
        chunk_overlap: Overlap tokens between consecutive chunks (default 50).

    Returns:
        List of TextNode objects.
    """
    splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    nodes = splitter.get_nodes_from_documents(documents)
    print(f"Total chunks created: {len(nodes)}")
    return nodes


# -- Step 4: Build vector index ------------------------------------------------

def build_index(nodes) -> VectorStoreIndex:
    """
    Build an in-memory VectorStoreIndex from a list of nodes.

    Args:
        nodes: List of TextNode objects (from chunk_documents).

    Returns:
        A VectorStoreIndex ready for retrieval.
    """
    index = VectorStoreIndex(nodes)
    print(f"VectorStoreIndex created with {len(nodes)} nodes.")
    return index


# -- Step 5: Create retriever --------------------------------------------------

def build_retriever(index: VectorStoreIndex, similarity_top_k: int = SIMILARITY_TOP_K):
    """
    Wrap the index as a dense retriever.

    Args:
        index:            A VectorStoreIndex.
        similarity_top_k: Number of top chunks to retrieve (default 10).

    Returns:
        A VectorIndexRetriever instance.
    """
    retriever = index.as_retriever(similarity_top_k=similarity_top_k)
    return retriever


# -- Step 6: Retrieve relevant chunks ------------------------------------------

def retrieve_chunks(retriever, query: str):
    """
    Run a dense retrieval query and return ranked nodes.

    Args:
        retriever: A VectorIndexRetriever (from build_retriever).
        query:     Natural-language query string.

    Returns:
        List of NodeWithScore objects, sorted by descending similarity.
    """
    retrieved_nodes = retriever.retrieve(query)
    print(f"Retrieved {len(retrieved_nodes)} chunks for query: '{query}'")
    return retrieved_nodes


# -- Step 7: Build zero-shot summarization prompt ------------------------------

def build_prompt(query: str, retrieved_nodes) -> str:
    """
    Construct a zero-shot prompt from the retrieved context chunks.

    Args:
        query:           The user question or summarization task.
        retrieved_nodes: NodeWithScore objects returned by retrieve_chunks.

    Returns:
        Formatted prompt string ready to be sent to the LLM.
    """
    context = "\n\n".join([node.text for node in retrieved_nodes])

    prompt = (
        "You are an expert AI assistant specialized in summarizing transcripts.\n\n"
        "Use ONLY the information provided in the context below.\n"
        "Do not invent or assume information that is not present.\n\n"
        "-------------------- CONTEXT --------------------\n\n"
        f"{context}\n\n"
        "-------------------------------------------------\n\n"
        "Task:\n"
        "Provide a structured summary including:\n\n"
        "1. Main Topic\n"
        "2. Key Concepts\n"
        "3. Important Discussions\n"
        "4. Conclusions\n"
        "5. Key Takeaways\n\n"
        "Keep the summary concise, informative, and under 300 words.\n\n"
        f"Question / Task: {query}"
    )

    return prompt


# -- Step 8: Call LLM ----------------------------------------------------------

def call_llm(
    prompt: str,
    hf_token: str | None = None,
    model: str = LLM_MODEL_NAME,
    temperature: float = LLM_TEMPERATURE,
    max_tokens: int = LLM_MAX_TOKENS,
) -> str:
    """
    Send the prompt to a Hugging Face Inference API model and return the response.

    Args:
        prompt:      Formatted prompt string (from build_prompt).
        hf_token:    HuggingFace API token. Falls back to HF_TOKEN env var.
        model:       HF model ID (default: Llama-3.1-8B-Instruct).
        temperature: Sampling temperature (default 0.2 for deterministic output).
        max_tokens:  Maximum tokens in the generated response (default 700).

    Returns:
        The LLM-generated summary string.
    """
    token = hf_token or os.environ.get("HF_TOKEN")
    if not token:
        raise ValueError(
            "A Hugging Face API token is required. "
            "Pass hf_token= or set the HF_TOKEN environment variable."
        )

    client = InferenceClient(api_key=token)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )

    summary = response.choices[0].message.content
    return summary


# -- Full pipeline -------------------------------------------------------------

def run_doc_to_llm_pipeline(
    transcript_path: str | Path,
    query: str = "Summarize the entire video.",
    hf_token: str | None = None,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    similarity_top_k: int = SIMILARITY_TOP_K,
) -> tuple:
    """
    End-to-end document-to-LLM pipeline:
        transcript .txt -> embed -> index -> retrieve -> prompt -> LLM -> summary

    Args:
        transcript_path:  Path to the transcript .txt file.
        query:            Summarization or Q&A query (default: full-video summary).
        hf_token:         HuggingFace API token (falls back to HF_TOKEN env var).
        chunk_size:       Tokens per chunk (default 300).
        chunk_overlap:    Overlap between chunks (default 50).
        similarity_top_k: Top-K chunks retrieved (default 10).

    Returns:
        Tuple of (summary_string, retrieved_nodes).
    """
    # 1. Embedding model
    load_embed_model()

    # 2. Load transcript
    documents = load_transcript(transcript_path)

    # 3. Chunk
    nodes = chunk_documents(documents, chunk_size, chunk_overlap)

    # 4. Index
    index = build_index(nodes)

    # 5. Retriever
    retriever = build_retriever(index, similarity_top_k)

    # 6. Retrieve
    retrieved_nodes = retrieve_chunks(retriever, query)

    # 7. Prompt
    prompt = build_prompt(query, retrieved_nodes)

    # 8. LLM call
    summary = call_llm(prompt, hf_token=hf_token)

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(summary)

    return summary, retrieved_nodes
