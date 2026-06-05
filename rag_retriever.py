import os

import numpy as np
from google import genai


class RAGRetriever:
    def __init__(self, api_key: str, embedding_model: str | None = None):
        self.client = genai.Client(api_key=api_key)
        self.embedding_model = embedding_model or os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        self.chunks = []
        self.embeddings = np.array([])
        self.embedding_batch_size = int(os.getenv("GEMINI_EMBEDDING_BATCH_SIZE", "100"))

    def index_chunks(self, chunks: list):
        """
        Embed prepared chunks. Each chunk must include title and text.
        Extra metadata such as source_id, file_name, and page_number is preserved.
        """
        new_chunks = [chunk for chunk in chunks if chunk.get("text", "").strip()]
        if not new_chunks:
            print("RAGRetriever: No chunks supplied for indexing.")
            return False

        texts_to_embed = [chunk["text"] for chunk in new_chunks]
        try:
            print(f"RAGRetriever: Embedding {len(new_chunks)} chunks using {self.embedding_model}...")
            embeddings = []
            for start in range(0, len(texts_to_embed), self.embedding_batch_size):
                end = start + self.embedding_batch_size
                batch = texts_to_embed[start:end]
                print(f"RAGRetriever: Embedding batch {start + 1}-{min(end, len(texts_to_embed))}...")
                response = self.client.models.embed_content(
                    model=self.embedding_model,
                    contents=batch,
                )
                embeddings.extend(emb.values for emb in response.embeddings)

            if len(embeddings) != len(new_chunks):
                raise RuntimeError(f"Expected {len(new_chunks)} embeddings, got {len(embeddings)}.")

            self.chunks = new_chunks
            self.embeddings = np.array(embeddings)
            print(f"RAGRetriever: Indexed {len(self.chunks)} chunks successfully.")
        except Exception as exc:
            print(f"RAGRetriever: Batch embedding failed: {exc}")
            return False

        return True

    def load_and_index_file(self, file_path: str):
        if not os.path.exists(file_path):
            print(f"RAGRetriever: File not found: {file_path}")
            return

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                content = file.read()
        except Exception as exc:
            print(f"RAGRetriever: Error reading file: {exc}")
            return

        chunks = []
        for part in content.split("### Topic:"):
            part = part.strip()
            if not part:
                continue

            lines = part.split("\n", 1)
            title = lines[0].strip()
            body = lines[1].strip() if len(lines) > 1 else ""
            chunks.append(
                {
                    "title": title,
                    "text": f"Topic: {title}\n{body}",
                    "source_id": "default-textbook",
                    "file_name": os.path.basename(file_path),
                    "page_number": None,
                }
            )

        if not chunks:
            print("RAGRetriever: No chunks found in file.")
            return

        return self.index_chunks(chunks)

    def retrieve(self, query: str, k: int = 2) -> list:
        if not self.chunks or self.embeddings.size == 0:
            print("RAGRetriever: No index loaded.")
            return []

        try:
            query_response = self.client.models.embed_content(
                model=self.embedding_model,
                contents=query,
            )
            query_embedding = np.array(query_response.embeddings[0].values)

            dot_product = np.dot(self.embeddings, query_embedding)
            norms = np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(query_embedding)
            norms[norms == 0] = 1.0
            similarities = dot_product / norms

            top_indices = np.argsort(similarities)[-k:][::-1]

            results = []
            for idx in top_indices:
                result = dict(self.chunks[idx])
                result["score"] = float(similarities[idx])
                results.append(result)
            return results
        except Exception as exc:
            print(f"RAGRetriever: Retrieval failed: {exc}")
            return []
