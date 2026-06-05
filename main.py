import os
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rag_retriever import RAGRetriever

load_dotenv()

app = FastAPI(
    title="Adaptive Tutor Backend",
    description="FastAPI backend for the subject-agnostic adaptive tutor prototype.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatHistoryItem(BaseModel):
    id: Optional[str] = None
    sender: str
    text: str
    timestamp: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    history: List[ChatHistoryItem] = Field(default_factory=list)
    language: str = "EN"
    mode: str = "step-step"


class RagSearchRequest(BaseModel):
    query: str
    k: int = 2


class SourceInfo(BaseModel):
    source_id: str
    file_name: str
    content_type: str
    processed_path: str
    chunk_count: int
    created_at: str
    preview_title: Optional[str] = None
    preview_text: Optional[str] = None


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_text(text: str, max_chars: int = 1200, overlap_chars: int = 160) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    chunks = []
    current = ""

    for paragraph in paragraphs:
      if len(paragraph) > max_chars:
          if current:
              chunks.append(current.strip())
              current = ""
          start = 0
          while start < len(paragraph):
              end = start + max_chars
              chunks.append(paragraph[start:end].strip())
              start = max(end - overlap_chars, end)
          continue

      candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
      if len(candidate) > max_chars and current:
          chunks.append(current.strip())
          current = paragraph
      else:
          current = candidate

    if current:
        chunks.append(current.strip())

    return chunks


def limit_pages_for_testing(pages: list[dict], max_pages: int) -> tuple[list[dict], bool]:
    if max_pages <= 0 or len(pages) <= max_pages:
        return pages, False
    return pages[:max_pages], True


def extract_txt(file_path: Path) -> list[dict]:
    text = normalize_text(file_path.read_text(encoding="utf-8", errors="ignore"))
    return [{"page_number": None, "text": text}] if text else []


def extract_pdf(file_path: Path) -> list[dict]:
    from pypdf import PdfReader

    reader = PdfReader(str(file_path))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = normalize_text(page.extract_text() or "")
        if text:
            pages.append({"page_number": index, "text": text})
    return pages


def build_chunks_from_pages(source_id: str, file_name: str, pages: list[dict]) -> list[dict]:
    chunks = []
    for page in pages:
        page_number = page["page_number"]
        page_label = f"Page {page_number}" if page_number else "Uploaded Text"
        for index, chunk_text in enumerate(split_text(page["text"]), start=1):
            title = f"{Path(file_name).stem} - {page_label}"
            if len(split_text(page["text"])) > 1:
                title = f"{title} Part {index}"
            chunks.append(
                {
                    "source_id": source_id,
                    "file_name": file_name,
                    "page_number": page_number,
                    "title": title,
                    "text": f"Topic: {title}\n{chunk_text}",
                }
            )
    return chunks


def append_source_manifest(source: SourceInfo):
    manifest_path = Path("data/sources.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        import json

        sources = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        sources = []

    sources.append(source.model_dump())

    import json

    manifest_path.write_text(json.dumps(sources, indent=2), encoding="utf-8")


def load_processed_chunks(source: SourceInfo) -> list[dict]:
    processed_path = Path(source.processed_path)
    if not processed_path.exists():
        return []

    raw_text = processed_path.read_text(encoding="utf-8", errors="ignore")
    blocks = [block.strip() for block in raw_text.split("### Chunk") if block.strip()]
    chunks = []

    for index, block in enumerate(blocks, start=1):
        match = re.match(r"Topic:\s*(.+?)\n(.*)", block, flags=re.DOTALL)
        if match:
            title = match.group(1).strip()
            text = block
        else:
            title = f"{Path(source.file_name).stem} Part {index}"
            text = f"Topic: {title}\n{block}"

        chunks.append(
            {
                "source_id": source.source_id,
                "file_name": source.file_name,
                "page_number": None,
                "title": title,
                "text": text,
            }
        )

    return chunks


def latest_manifest_source() -> Optional[SourceInfo]:
    manifest_path = Path("data/sources.json")
    if not manifest_path.exists():
        return None

    try:
        sources = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"AdaptiveTutorEngine: could not read source manifest: {exc}")
        return None

    for item in reversed(sources):
        try:
            source = SourceInfo(**item)
        except Exception:
            continue
        if Path(source.processed_path).exists():
            return source

    return None


class AdaptiveTutorEngine:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.has_key = bool(self.api_key and self.api_key != "MY_GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
        self.rag_source_file = os.getenv("RAG_SOURCE_FILE", "data/textbook/chapter_1.txt")
        self.rag_min_score = float(os.getenv("RAG_MIN_SCORE", "0.55"))
        self.rag_candidate_min_score = float(os.getenv("RAG_CANDIDATE_MIN_SCORE", "0.35"))
        self.rag_context_check_k = int(os.getenv("RAG_CONTEXT_CHECK_K", "3"))
        self.upload_dir = Path(os.getenv("UPLOAD_DIR", "data/uploads"))
        self.processed_source_dir = Path(os.getenv("PROCESSED_SOURCE_DIR", "data/processed"))
        self.max_upload_pages = int(os.getenv("MAX_UPLOAD_PAGES", "35"))
        self.max_upload_chunks = int(os.getenv("MAX_UPLOAD_CHUNKS", "90"))
        self.client = None
        self.retriever = None
        self.current_source: Optional[SourceInfo] = None

        if not self.has_key:
            print("AdaptiveTutorEngine: running in demo mode because GEMINI_API_KEY is not configured.")
            return

        try:
            from google import genai

            self.client = genai.Client(api_key=self.api_key)
            self.retriever = RAGRetriever(self.api_key)
            restored_source = latest_manifest_source()
            restored = False
            if restored_source:
                restored_chunks = load_processed_chunks(restored_source)
                restored = self.retriever.index_chunks(restored_chunks)
                if restored:
                    preview = self.retriever.chunks[0] if self.retriever.chunks else {}
                    restored_source.chunk_count = len(self.retriever.chunks)
                    restored_source.preview_title = restored_source.preview_title or preview.get("title")
                    restored_source.preview_text = restored_source.preview_text or preview.get("text")
                    self.current_source = restored_source
                    self.rag_source_file = restored_source.processed_path

            if not restored:
                self.retriever.load_and_index_file(self.rag_source_file)
                preview = self.retriever.chunks[0] if self.retriever and self.retriever.chunks else {}
                self.current_source = SourceInfo(
                    source_id="default-textbook",
                    file_name=Path(self.rag_source_file).name,
                    content_type="text/plain",
                    processed_path=self.rag_source_file,
                    chunk_count=len(self.retriever.chunks) if self.retriever else 0,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    preview_title=preview.get("title"),
                    preview_text=preview.get("text"),
                )
            print(f"AdaptiveTutorEngine: Gemini client ready; RAG source={self.rag_source_file}")
        except Exception as exc:
            print(f"AdaptiveTutorEngine: startup warning: {exc}")
            self.client = None
            self.retriever = None

    def ingest_upload(self, upload: UploadFile) -> SourceInfo:
        if not self.has_key:
            raise HTTPException(status_code=400, detail="GEMINI_API_KEY is required before uploaded sources can be indexed.")

        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in {".pdf", ".txt"}:
            raise HTTPException(status_code=400, detail="Only PDF and TXT uploads are supported in this prototype.")

        source_id = str(uuid.uuid4())
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", upload.filename or f"source{suffix}")
        stored_path = self.upload_dir / f"{source_id}_{safe_name}"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.processed_source_dir.mkdir(parents=True, exist_ok=True)

        with stored_path.open("wb") as output:
            shutil.copyfileobj(upload.file, output)

        try:
            pages = extract_pdf(stored_path) if suffix == ".pdf" else extract_txt(stored_path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not extract text from uploaded file: {exc}") from exc

        if not pages:
            raise HTTPException(
                status_code=400,
                detail="No selectable text was extracted. This may be a scanned/image-only PDF and will need OCR support.",
            )

        pages, pages_were_limited = limit_pages_for_testing(pages, self.max_upload_pages)
        chunks = build_chunks_from_pages(source_id, safe_name, pages)
        if not chunks:
            raise HTTPException(status_code=400, detail="Text was extracted, but no usable chunks were created.")

        chunks_were_limited = len(chunks) > self.max_upload_chunks
        if chunks_were_limited:
            chunks = chunks[: self.max_upload_chunks]

        processed_path = self.processed_source_dir / f"{source_id}.txt"
        processed_path.write_text("\n\n### Chunk\n\n".join(chunk["text"] for chunk in chunks), encoding="utf-8")

        if not self.retriever:
            self.retriever = RAGRetriever(self.api_key)
        indexed = self.retriever.index_chunks(chunks)
        if not indexed:
            raise HTTPException(
                status_code=429,
                detail=(
                    "The source was extracted, but embedding/indexing failed. "
                    "This is usually an API quota issue. Try a smaller chapter PDF or wait for quota reset."
                ),
            )
        self.rag_source_file = str(processed_path)

        source = SourceInfo(
            source_id=source_id,
            file_name=safe_name,
            content_type=upload.content_type or "application/octet-stream",
            processed_path=str(processed_path),
            chunk_count=len(chunks),
            created_at=datetime.now(timezone.utc).isoformat(),
            preview_title=chunks[0]["title"],
            preview_text=chunks[0]["text"],
        )
        self.current_source = source
        append_source_manifest(source)
        if pages_were_limited or chunks_were_limited:
            print(
                "AdaptiveTutorEngine: upload indexed with testing limits "
                f"(pages_limited={pages_were_limited}, chunks_limited={chunks_were_limited}, chunks={len(chunks)})."
            )
        return source

    def retrieve_candidates(self, query: str, k: int = 3) -> list:
        if not self.retriever:
            return []

        results = self.retriever.retrieve(query, k=k)
        return [item for item in results if item.get("score", 0) >= self.rag_candidate_min_score]

    def retrieve_sources(self, query: str, k: int = 2) -> list:
        results = self.retrieve_candidates(query, k=k)
        return [item for item in results if item.get("score", 0) >= self.rag_min_score]

    def build_source_context(self, sources: list) -> str:
        blocks = []
        for index, source in enumerate(sources, start=1):
            blocks.append(
                f"[Source {index}: {source['title']} | relevance={source['score']:.3f}]\n"
                f"{source['text']}"
            )
        return "\n\n".join(blocks)

    def parse_json_object(self, text: str) -> dict:
        try:
            return json.loads(text)
        except Exception:
            pass

        match = re.search(r"\{.*\}", text or "", flags=re.DOTALL)
        if not match:
            return {}

        try:
            return json.loads(match.group(0))
        except Exception:
            return {}

    def check_context_sufficiency(self, question: str, sources: list) -> dict:
        if not sources:
            return {
                "answerable": False,
                "reason": "No candidate chunks were retrieved from the active source.",
                "search_query": question,
            }

        if not self.client:
            return {
                "answerable": bool(sources),
                "reason": "Gemini context checking is unavailable, so the system used retrieval score only.",
                "search_query": question,
            }

        source_context = self.build_source_context(sources)
        prompt = (
            "You are checking retrieval quality for a source-grounded tutoring app.\n"
            "Decide whether the retrieved source context is enough to answer the student's question accurately.\n"
            "Mark answerable=false if the chunks only share broad subject words, are merely adjacent, or would require outside knowledge.\n"
            "Return strict JSON only with these fields:\n"
            "{\"answerable\": boolean, \"reason\": string, \"search_query\": string}\n\n"
            f"Student question:\n{question}\n\n"
            f"Retrieved source context:\n{source_context[:6000]}"
        )

        try:
            from google.genai import types

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            parsed = self.parse_json_object(response.text or "")
            return {
                "answerable": bool(parsed.get("answerable")),
                "reason": str(parsed.get("reason") or "Context check did not provide a reason."),
                "search_query": str(parsed.get("search_query") or question),
            }
        except Exception as exc:
            print(f"AdaptiveTutorEngine: context check error: {exc}")
            top_score = max((source.get("score", 0) for source in sources), default=0)
            return {
                "answerable": top_score >= self.rag_min_score,
                "reason": "Context check failed, so the system fell back to retrieval score.",
                "search_query": question,
            }

    def retrieve_checked_sources(self, question: str) -> dict:
        first_sources = self.retrieve_candidates(question, k=self.rag_context_check_k)
        first_check = self.check_context_sufficiency(question, first_sources)
        attempts = [
            {
                "query": question,
                "answerable": first_check["answerable"],
                "reason": first_check["reason"],
            }
        ]

        if first_check["answerable"]:
            return {
                "sources": first_sources,
                "status": "grounded",
                "note": first_check["reason"],
                "attempts": attempts,
            }

        retry_query = first_check.get("search_query") or question
        if retry_query.strip().lower() != question.strip().lower():
            retry_sources = self.retrieve_candidates(retry_query, k=self.rag_context_check_k)
            retry_check = self.check_context_sufficiency(question, retry_sources)
            attempts.append(
                {
                    "query": retry_query,
                    "answerable": retry_check["answerable"],
                    "reason": retry_check["reason"],
                }
            )

            if retry_check["answerable"]:
                return {
                    "sources": retry_sources,
                    "status": "grounded_after_retry",
                    "note": retry_check["reason"],
                    "attempts": attempts,
                }

            return {
                "sources": retry_sources or first_sources,
                "status": "insufficient_context",
                "note": retry_check["reason"],
                "attempts": attempts,
            }

        return {
            "sources": first_sources,
            "status": "insufficient_context",
            "note": first_check["reason"],
            "attempts": attempts,
        }

    def build_system_instruction(self, language: str, mode: str, has_sources: bool) -> str:
        instruction = (
            "You are a subject-agnostic adaptive tutor for university students. "
            "Your job is to help students understand, not merely give final answers. "
            "Do not dump or copy long passages from the source. Synthesize the source into a short, flexible explanation. "
            "Use at most one very short quoted phrase only if it is necessary. "
        )

        if has_sources:
            instruction += (
                "Use the retrieved source context as your main ground truth. "
                "Cite the source title when you use it. "
                "If the source is only loosely related or does not directly support the student's question, "
                "say the current uploaded source does not cover the question and do not answer from outside knowledge. "
                "Structure the response as: core idea, explanation in the selected mode, why it matters, and a quick check question. "
            )
        else:
            instruction += (
                "No relevant source context was retrieved. Say that the current uploaded source does not directly cover the question, "
                "and ask the student to upload a relevant source or ask a question from the current material. "
            )

        mode_instructions = {
            "analogy": "Start with a simple everyday analogy, then connect it back to the academic concept.",
            "step-step": "Explain with numbered, clear step-by-step reasoning.",
            "visual": "Use spatial or visual descriptions, movement, flow, or sequence where possible.",
            "peer": "Use a friendly peer-study tone while staying accurate and concise.",
        }
        instruction += mode_instructions.get(mode, mode_instructions["step-step"])

        instruction += (
            f" Reply in the language matching this code: {language}. "
            "(EN = English, FR = French, SW = Swahili, HA = Hausa, YO = Yoruba). "
            "End with one short check-for-understanding question."
        )
        return instruction

    def build_general_instruction(self, language: str, mode: str) -> str:
        mode_instructions = {
            "analogy": "Use a simple analogy, then connect it back to the academic concept.",
            "step-step": "Use numbered, clear step-by-step reasoning.",
            "visual": "Use spatial or visual descriptions, movement, flow, or sequence where possible.",
            "peer": "Use a friendly peer-study tone while staying accurate and concise.",
        }
        return (
            "You are an adaptive tutor. The uploaded source did not contain enough context for the question. "
            "Give a cautious general explanation, but clearly avoid pretending it came from the uploaded source. "
            f"{mode_instructions.get(mode, mode_instructions['step-step'])} "
            f"Reply in the language matching this code: {language}. "
            "(EN = English, FR = French, SW = Swahili, HA = Hausa, YO = Yoruba). "
            "Keep it concise and end with one check-for-understanding question."
        )

    def generate_general_fallback(self, question: str, language: str, mode: str) -> str:
        prefix = (
            "During my search, I did not find enough context in the uploaded source material "
            "to answer your question properly. I retried the retrieval, but the source still did not support the question. "
            "So the explanation below is a general answer, not a source-grounded answer.\n\n"
        )

        if not self.client:
            return (
                prefix +
                "I cannot generate a general explanation right now because the chat model is unavailable. "
                f"Your question was: {question}"
            )

        try:
            from google.genai import types

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[{"role": "user", "parts": [{"text": question}]}],
                config=types.GenerateContentConfig(
                    system_instruction=self.build_general_instruction(language, mode),
                    temperature=0.35,
                ),
            )
            return prefix + (response.text or f"Question: {question}")
        except Exception as exc:
            print(f"AdaptiveTutorEngine: general fallback error: {exc}")
            return (
                prefix +
                "I could not generate the general fallback because the chat model failed. "
                f"Your question was: {question}"
            )

    def source_summary(self, source: dict) -> dict:
        text = source.get("text", "")
        title = source.get("title", "Retrieved Source")
        body = re.sub(r"^Topic:\s*.+?\n", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
        body = body.replace("â€”", "-")

        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", body) if part.strip()]
        return {
            "title": title,
            "core": sentences[0] if sentences else "The retrieved source contains the closest available explanation.",
            "steps": sentences[1:4] if len(sentences) > 1 else sentences[:1],
            "why": "This answer is limited to the retrieved source text, so it should be tested against the source panel.",
        }

    def synthesize_fallback(self, prompt: str, source: dict, mode: str) -> str:
        summary = self.source_summary(source)
        title = summary["title"]
        core = summary["core"]
        steps = summary["steps"]
        why = summary["why"]

        if mode == "analogy":
            return (
                f"Using {title}: think of the retrieved passage as the page currently open on your desk. "
                "The safest answer is the one that stays close to what that page actually says.\n\n"
                f"Core idea: {core} "
                f"{why}\n\n"
                "Quick check: which sentence in the source best supports that idea?"
            )

        if mode == "visual":
            return (
                f"Using {title}: picture the process as a short flow.\n\n"
                + "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))
                + f"\n\nWhy it matters: {why}\n\n"
                "Quick check: can you draw or describe the flow in three arrows?"
            )

        if mode == "peer":
            return (
                f"Using {title}: the simple version is this: {core}\n\n"
                f"So if your lecturer asks what is happening, say it like this: {steps[0] if steps else core} "
                f"Then add the result: {steps[-1] if steps else why}\n\n"
                "Quick check: how would you explain that to a classmate in one sentence?"
            )

        return (
            f"Using {title}, here is the idea step by step:\n\n"
            + "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))
            + f"\n\nCore takeaway: {core} {why}\n\n"
            "Quick check: which part of the uploaded source supports this answer?"
        )

    def fallback_reply(self, prompt: str, sources: list, mode: str = "step-step") -> str:
        if sources:
            return self.synthesize_fallback(prompt, sources[0], mode)

        return (
            "I could not find a strong match in the currently indexed source file. "
            "This may mean the question is outside the uploaded material, or the RAG threshold/chunking needs adjustment. "
            f"Your question was: {prompt}"
        )

    def chat(self, payload: ChatRequest) -> dict:
        retrieval = self.retrieve_checked_sources(payload.message)
        sources = retrieval["sources"] if retrieval["status"] in {"grounded", "grounded_after_retry"} else []
        candidate_sources = retrieval["sources"]
        source_context = self.build_source_context(sources)

        if not self.client:
            return {
                "text": self.fallback_reply(payload.message, sources, payload.mode),
                "sources": sources,
                "candidate_sources": candidate_sources,
                "grounding_status": retrieval["status"],
                "retrieval_note": retrieval["note"],
                "retrieval_attempts": retrieval["attempts"],
                "warning": "Demo fallback active because Gemini chat is not configured.",
            }

        if retrieval["status"] == "insufficient_context":
            return {
                "text": self.generate_general_fallback(payload.message, payload.language, payload.mode),
                "sources": [],
                "candidate_sources": candidate_sources,
                "grounding_status": "insufficient_context",
                "retrieval_note": retrieval["note"],
                "retrieval_attempts": retrieval["attempts"],
            }

        try:
            contents = []
            for item in payload.history[-6:]:
                contents.append(
                    {
                        "role": "model" if item.sender == "tutor" else "user",
                        "parts": [{"text": item.text}],
                    }
                )

            if source_context:
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": (
                                    "Retrieved source context for the next student question:\n\n"
                                    f"{source_context}"
                                )
                            }
                        ],
                    }
                )

            contents.append({"role": "user", "parts": [{"text": payload.message}]})

            from google.genai import types

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=self.build_system_instruction(
                        payload.language,
                        payload.mode,
                        has_sources=bool(sources),
                    ),
                    temperature=0.4,
                ),
            )

            return {
                "text": response.text or self.fallback_reply(payload.message, sources, payload.mode),
                "sources": sources,
                "candidate_sources": candidate_sources,
                "grounding_status": retrieval["status"],
                "retrieval_note": retrieval["note"],
                "retrieval_attempts": retrieval["attempts"],
            }
        except Exception as exc:
            print(f"AdaptiveTutorEngine: chat model error: {exc}")
            return {
                "text": self.fallback_reply(payload.message, sources, payload.mode),
                "sources": sources,
                "candidate_sources": candidate_sources,
                "grounding_status": retrieval["status"],
                "retrieval_note": retrieval["note"],
                "retrieval_attempts": retrieval["attempts"],
                "warning": f"Model fallback active: {exc}",
            }


engine = AdaptiveTutorEngine()


@app.post("/api/chat")
async def chat_endpoint(payload: ChatRequest):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message is required.")
    return engine.chat(payload)


@app.post("/api/rag/search")
async def rag_search_endpoint(payload: RagSearchRequest):
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query is required.")

    return {
        "query": payload.query,
        "source_file": engine.rag_source_file,
        "min_score": engine.rag_min_score,
        "results": engine.retrieve_sources(payload.query, k=payload.k),
    }


@app.post("/api/sources/upload")
async def upload_source_endpoint(file: UploadFile = File(...)):
    return {
        "source": engine.ingest_upload(file),
        "message": "Source uploaded, extracted, chunked, and indexed successfully.",
    }


@app.get("/api/sources/current")
async def current_source_endpoint():
    return {
        "source": engine.current_source,
        "rag_source_file": engine.rag_source_file,
        "rag_enabled": engine.retriever is not None,
    }


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "backend": "fastapi",
        "model_enabled": engine.client is not None,
        "rag_enabled": engine.retriever is not None,
        "rag_source_file": engine.rag_source_file,
        "rag_min_score": engine.rag_min_score,
        "upload_enabled": engine.has_key,
        "max_upload_pages": engine.max_upload_pages,
        "max_upload_chunks": engine.max_upload_chunks,
        "current_source": engine.current_source,
    }


dist_dir = os.path.join(os.getcwd(), "dist")
if os.path.exists(dist_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_dir, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        target_path = os.path.join(dist_dir, full_path)
        if full_path and os.path.exists(target_path) and os.path.isfile(target_path):
            return FileResponse(target_path)
        return FileResponse(os.path.join(dist_dir, "index.html"))
else:

    @app.get("/")
    async def fallback_root():
        return {
            "status": "online",
            "message": "FastAPI is running. Start the Vite frontend with npm.cmd run dev.",
        }
