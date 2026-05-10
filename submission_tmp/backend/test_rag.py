import requests
import time
import json
import os

BASE_URL = "http://localhost:8000"
DOC_PATH = "../Project Task-1.pdf"

def wait_for_server():
    print("Waiting for server to start...")
    for _ in range(30):
        try:
            res = requests.get(f"{BASE_URL}/health")
            if res.status_code == 200:
                print("Server is up!")
                return True
        except:
            time.sleep(2)
    print("Server did not start in time.")
    return False

def test_rag():
    if not wait_for_server():
        return
        
    print("\n1. Uploading Document...")
    with open(DOC_PATH, "rb") as f:
        files = {"file": ("Project Task-1.pdf", f, "application/pdf")}
        response = requests.post(f"{BASE_URL}/upload", files=files)
        
    if response.status_code == 200:
        print("Upload Success:", json.dumps(response.json(), indent=2))
    else:
        print("Upload Failed:", response.text)
        return

    print("\n2. Querying RAG System...")
    query = {
        "question": "What is the deadline for Task-1 and what needs to be submitted?",
        "top_k": 3,
        "use_reranking": True
    }
    
    response = requests.post(f"{BASE_URL}/query", json=query)
    
    if response.status_code == 200:
        data = response.json()
        print("\n=== ANSWER ===")
        print(data["answer"])
        print("\n=== SOURCES ===")
        print(data["sources"])
        print("\n=== TOP CONTEXT CHUNK ===")
        print(data["context_chunks"][0]["text"] if data["context_chunks"] else "None")
    else:
        print("Query Failed:", response.text)

if __name__ == "__main__":
    test_rag()
