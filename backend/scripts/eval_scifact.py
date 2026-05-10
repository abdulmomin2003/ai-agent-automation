"""
Evaluation script for BEIR SciFact using the project's retriever.

Outputs JSON metrics to backend/data/beir/scifact_eval_metrics.json.
"""

from __future__ import annotations

import os
import sys

import time
import json
from beir.datasets.data_loader import GenericDataLoader
from beir.retrieval.evaluation import EvaluateRetrieval

# Ensure backend root is on sys.path when running from repo root
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from embeddings import EmbeddingService
from vector_store import VectorStore
from retriever import HybridRetriever

DATASET = "scifact"
DATA_DIR = os.path.join(os.getcwd(), "data", "beir", DATASET)
VSTORE_DIR = os.path.join(os.getcwd(), "vector_db_eval_scifact")
TOP_K = 10
BATCH = 64
MAX_QUERIES = 10  # speed cap for evaluation
MAX_DOCS = 200    # speed cap for corpus size


def clear_dir(path: str) -> None:
    if not os.path.exists(path):
        return
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))


def results_from_docs(docs, score_key="score"):
    out = {}
    for d in docs:
        score = d.get(score_key, d.get("rrf_score", d.get("rerank_score", 0.0)))
        out[d["id"]] = float(score)
    return out


def evaluate_method(name, method_fn, queries, qrels):
    t0 = time.time()
    results = {}
    for qid, query in queries.items():
        docs = method_fn(query)
        results[qid] = results_from_docs(docs)
    elapsed = time.time() - t0

    evaluator = EvaluateRetrieval()
    k_values = [1, 3, 5, 10]
    ndcg, _map, recall, precision = evaluator.evaluate(qrels, results, k_values)

    return {
        "name": name,
        "ndcg@10": ndcg["NDCG@10"],
        "recall@5": recall["Recall@5"],
        "precision@5": precision["P@5"],
        "avg_latency_s": elapsed / max(len(queries), 1),
    }


def main() -> None:
    if not os.path.exists(DATA_DIR):
        raise RuntimeError(
            f"Dataset not found at {DATA_DIR}. Run the downloader first."
        )

    corpus, queries, qrels = GenericDataLoader(DATA_DIR).load(split="test")

    query_items = list(queries.items())[:MAX_QUERIES]
    queries = {qid: q for qid, q in query_items}
    qrels = {qid: qrels[qid] for qid in queries.keys() if qid in qrels}

    clear_dir(VSTORE_DIR)
    os.makedirs(VSTORE_DIR, exist_ok=True)

    embedder = EmbeddingService()
    store = VectorStore(persist_dir=VSTORE_DIR)

    ids = []
    texts = []
    metas = []
    for i, (doc_id, doc) in enumerate(corpus.items()):
        if i >= MAX_DOCS:
            break
        title = doc.get("title", "") or ""
        body = doc.get("text", "") or ""
        full_text = (title + "\n" + body).strip()
        if not full_text:
            continue
        ids.append(doc_id)
        texts.append(full_text)
        metas.append({"source": doc_id})

    embeddings = []
    for i in range(0, len(texts), BATCH):
        embeddings.extend(embedder.embed_batch(texts[i:i + BATCH]))

    store.add_documents(ids=ids, texts=texts, embeddings=embeddings, metadatas=metas)

    retriever = HybridRetriever(vector_store=store, embedding_service=embedder)
    retriever.refresh_index()

    metrics = []
    metrics.append(evaluate_method(
        "Dense-only",
        lambda q: store.search(embedder.embed_query(q), top_k=TOP_K),
        queries,
        qrels,
    ))
    metrics.append(evaluate_method(
        "BM25-only",
        lambda q: retriever._bm25_search(q, TOP_K),
        queries,
        qrels,
    ))
    metrics.append(evaluate_method(
        "Hybrid (no rerank)",
        lambda q: retriever.retrieve(q, top_k=TOP_K, use_reranking=False),
        queries,
        qrels,
    ))
    metrics.append(evaluate_method(
        "Hybrid + rerank",
        lambda q: retriever.retrieve(q, top_k=TOP_K, use_reranking=True),
        queries,
        qrels,
    ))

    result = {
        "dataset": DATASET,
        "num_queries": len(queries),
        "top_k": TOP_K,
        "metrics": metrics,
    }

    result_path = os.path.join(os.getcwd(), "data", "beir", "scifact_eval_metrics.json")
    os.makedirs(os.path.dirname(result_path), exist_ok=True)
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
