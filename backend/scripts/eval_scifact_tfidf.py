"""
Evaluation script for BEIR SciFact using TF-IDF + BM25 baselines.

Outputs JSON metrics to data/beir/scifact_eval_metrics.json.
"""

from __future__ import annotations

import os
import json
import time
from typing import Dict, List, Tuple

import numpy as np
from beir.datasets.data_loader import GenericDataLoader
from beir.retrieval.evaluation import EvaluateRetrieval
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer

DATASET = "scifact"
DATA_DIR = os.path.join(os.getcwd(), "data", "beir", DATASET)
TOP_K = 10
MAX_QUERIES = 100  # speed cap


def tokenize(text: str) -> List[str]:
    return [t for t in text.lower().split() if len(t) > 1]


def rrf_fuse(
    dense_ids: List[str],
    sparse_ids: List[str],
    k: int = 60,
    dense_weight: float = 0.7,
    sparse_weight: float = 0.3,
) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for rank, doc_id in enumerate(dense_ids):
        scores[doc_id] = scores.get(doc_id, 0.0) + dense_weight / (k + rank + 1)
    for rank, doc_id in enumerate(sparse_ids):
        scores[doc_id] = scores.get(doc_id, 0.0) + sparse_weight / (k + rank + 1)
    return scores


def evaluate_method(name: str, results: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    evaluator = EvaluateRetrieval()
    k_values = [1, 3, 5, 10]
    ndcg, _map, recall, precision = evaluator.evaluate(qrels, results, k_values)
    return {
        "name": name,
        "ndcg@10": ndcg["NDCG@10"],
        "recall@5": recall["Recall@5"],
        "precision@5": precision["P@5"],
    }


if not os.path.exists(DATA_DIR):
    raise RuntimeError(f"Dataset not found at {DATA_DIR}. Run the downloader first.")

corpus, queries, qrels = GenericDataLoader(DATA_DIR).load(split="test")

# Limit queries for faster runtime
query_items = list(queries.items())[:MAX_QUERIES]
queries = {qid: q for qid, q in query_items}
qrels = {qid: qrels[qid] for qid in queries.keys() if qid in qrels}

# Build corpus lists
corpus_ids: List[str] = []
corpus_texts: List[str] = []
for doc_id, doc in corpus.items():
    title = doc.get("title", "") or ""
    body = doc.get("text", "") or ""
    full_text = (title + "\n" + body).strip()
    if not full_text:
        continue
    corpus_ids.append(doc_id)
    corpus_texts.append(full_text)

# TF-IDF dense baseline
vectorizer = TfidfVectorizer(max_features=50000, ngram_range=(1, 2))
X = vectorizer.fit_transform(corpus_texts)

# BM25 sparse baseline
bm25_corpus = [tokenize(t) for t in corpus_texts]
bm25 = BM25Okapi(bm25_corpus)

results_dense: Dict[str, Dict[str, float]] = {}
results_bm25: Dict[str, Dict[str, float]] = {}
results_hybrid: Dict[str, Dict[str, float]] = {}

start = time.time()
for qid, query in queries.items():
    # Dense TF-IDF
    q_vec = vectorizer.transform([query])
    scores = (X @ q_vec.T).toarray().ravel()
    top_idx = np.argsort(-scores)[:TOP_K]
    dense_ids = [corpus_ids[i] for i in top_idx]
    results_dense[qid] = {corpus_ids[i]: float(scores[i]) for i in top_idx}

    # BM25
    bm25_scores = bm25.get_scores(tokenize(query))
    top_idx_bm25 = np.argsort(-bm25_scores)[:TOP_K]
    sparse_ids = [corpus_ids[i] for i in top_idx_bm25]
    results_bm25[qid] = {corpus_ids[i]: float(bm25_scores[i]) for i in top_idx_bm25}

    # Hybrid RRF
    fused = rrf_fuse(dense_ids, sparse_ids)
    fused_sorted = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:TOP_K]
    results_hybrid[qid] = {doc_id: float(score) for doc_id, score in fused_sorted}

elapsed = time.time() - start

metrics = []
metrics.append(evaluate_method("TF-IDF dense", results_dense))
metrics.append(evaluate_method("BM25", results_bm25))
metrics.append(evaluate_method("Hybrid (RRF)", results_hybrid))

result = {
    "dataset": DATASET,
    "num_docs": len(corpus_ids),
    "num_queries": len(queries),
    "metrics": metrics,
    "avg_latency_s": elapsed / max(len(queries), 1),
}

result_path = os.path.join(os.getcwd(), "data", "beir", "scifact_eval_metrics.json")
os.makedirs(os.path.dirname(result_path), exist_ok=True)
with open(result_path, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2)

print(json.dumps(result, indent=2))
