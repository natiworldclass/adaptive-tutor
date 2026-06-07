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
    current_hint_level: int = Field(default=1, ge=1, le=4)
    current_check_difficulty: str = "diagnostic"
    auto_hint: bool = True
    active_question: Optional[str] = None


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
    detected_title: Optional[str] = None
    subject: Optional[str] = None
    chapters: list[dict] = Field(default_factory=list)
    concept_count: int = 0
    concept_graph_path: Optional[str] = None
    processed_chunks_path: Optional[str] = None


HINT_STRATEGIES = {
    1: "orient",
    2: "narrow",
    3: "similar_example",
    4: "full_reasoning",
}


HINT_LABELS = {
    1: "Orienting",
    2: "Narrowing",
    3: "Similar Example",
    4: "Full Reasoning",
}


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


def guess_subject_from_text(text: str, file_name: str = "") -> str:
    haystack = f"{file_name}\n{text}".lower()
    subject_keywords = {
        "Education Technology": ["adaptive tutor", "ai tutor", "generic ai", "students", "textbook", "curriculum", "learning profile"],
        "Mathematics": ["mathematics", "maths", "algebra", "geometry", "calculus", "equation", "trigonometry"],
        "Physical Sciences": ["physical sciences", "physics", "chemistry", "matter", "force", "energy", "atom"],
        "Biology": ["biology", "photosynthesis", "cell", "enzyme", "organism", "genetics", "ecology"],
        "Computer Science": ["computer science", "programming", "algorithm", "data structure", "software"],
        "Economics": ["economics", "market", "demand", "supply", "inflation", "production"],
        "English": ["english", "literature", "grammar", "poem", "essay", "comprehension"],
    }
    best_subject = "General"
    best_score = 0
    for subject, keywords in subject_keywords.items():
        score = sum(1 for keyword in keywords if keyword in haystack)
        if score > best_score:
            best_subject = subject
            best_score = score
    return best_subject


def infer_title_from_pages(file_name: str, pages: list[dict]) -> str:
    stem = Path(file_name).stem.replace("_", " ").strip()
    first_text = "\n".join(page.get("text", "") for page in pages[:2])
    candidates = []
    for line in first_text.splitlines()[:24]:
        clean = re.sub(r"\s+", " ", line).strip(" -:\t")
        if 6 <= len(clean) <= 90 and not clean.lower().startswith(("page ", "chapter ")):
            alpha_ratio = sum(char.isalpha() for char in clean) / max(len(clean), 1)
            if alpha_ratio > 0.45:
                candidates.append(clean)
    return candidates[0] if candidates else stem


def detect_page_chapter(text: str) -> tuple[Optional[int], Optional[str]]:
    match = re.search(r"\bchapter\s+(\d+|[ivxlcdm]+)\b[:\s-]*(.{0,80})", text, flags=re.IGNORECASE)
    if not match:
        return None, None

    raw_number = match.group(1)
    chapter_title = re.sub(r"\s+", " ", match.group(2)).strip(" -:\t")
    try:
        chapter_number = int(raw_number)
    except ValueError:
        roman_values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
        total = 0
        previous = 0
        for char in reversed(raw_number.lower()):
            value = roman_values.get(char, 0)
            total += -value if value < previous else value
            previous = max(previous, value)
        chapter_number = total or None
    return chapter_number, chapter_title or None


def extract_concept_candidates(text: str, max_items: int = 8) -> list[str]:
    """Extract likely concept phrases from a text chunk using frequency analysis.
    No hardcoded keywords — works for any subject.
    """
    stopwords = {
        "about", "after", "again", "because", "before", "between", "chapter", "could", "every", "example",
        "first", "from", "have", "into", "learn", "learning", "more", "other", "page", "problem", "source",
        "student", "students", "their", "there", "these", "thing", "this", "through", "using", "where", "which",
        "while", "with", "would", "your", "doesn", "pages", "expected", "result", "better", "know", "what",
    }
    concepts = []

    # Pick up capitalised section headings generically (any heading-like line)
    for line in text.splitlines():
        clean = re.sub(r"\s+", " ", line).strip(" -:\t")
        if not clean:
            continue
        # Match lines that look like headings: start with a capital, short, no sentence punctuation
        heading_match = re.match(r"^([A-Z][A-Za-z0-9 ,:;'-]{4,79})\.?$", clean)
        if heading_match:
            candidate = re.sub(r"[^A-Za-z0-9 '-]", "", heading_match.group(1)).strip()
            if 5 <= len(candidate) <= 80 and candidate.title() not in concepts:
                concepts.append(candidate.title())
        if len(concepts) >= max_items // 2:
            break

    phrases = re.findall(r"\b[A-Za-z][A-Za-z0-9-]{4,}(?:\s+[A-Za-z][A-Za-z0-9-]{4,}){1,2}\b", text)
    counts: dict[str, int] = {}
    for phrase in phrases:
        clean = re.sub(r"\s+", " ", phrase).strip().lower()
        words = clean.split()
        if any(word in stopwords for word in words) or len(clean) < 8:
            continue
        counts[clean] = counts.get(clean, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (item[1], len(item[0])), reverse=True)
    for phrase, _count in ranked:
        concept = phrase.title()
        if concept not in concepts:
            concepts.append(concept)
        if len(concepts) >= max_items:
            break
    return concepts[:max_items]


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
        chapter_number, chapter_title = detect_page_chapter(page["text"])
        page_chunks = split_text(page["text"])
        for index, chunk_text in enumerate(page_chunks, start=1):
            title = f"{Path(file_name).stem} - {page_label}"
            if len(page_chunks) > 1:
                title = f"{title} Part {index}"
            chunks.append(
                {
                    "source_id": source_id,
                    "file_name": file_name,
                    "page_number": page_number,
                    "chapter_number": chapter_number,
                    "chapter_title": chapter_title,
                    "concept_tags": extract_concept_candidates(chunk_text, max_items=6),
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
    if source.processed_chunks_path and Path(source.processed_chunks_path).exists():
        try:
            chunks = json.loads(Path(source.processed_chunks_path).read_text(encoding="utf-8"))
            if isinstance(chunks, list):
                return chunks
        except Exception as exc:
            print(f"AdaptiveTutorEngine: could not read chunk sidecar: {exc}")

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

        page_match = re.search(r"\bPage\s+(\d+)\b", title, flags=re.IGNORECASE)
        page_number = int(page_match.group(1)) if page_match else None
        chunks.append(
            {
                "source_id": source.source_id,
                "file_name": source.file_name,
                "page_number": page_number,
                "chapter_number": None,
                "chapter_title": None,
                "concept_tags": extract_concept_candidates(text, max_items=6),
                "title": title,
                "text": text,
            }
        )

    return chunks


def read_json_file(path: Optional[str], fallback):
    if not path:
        return fallback
    try:
        json_path = Path(path)
        if json_path.exists():
            return json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"AdaptiveTutorEngine: could not read JSON file {path}: {exc}")
    return fallback


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
        self.concept_graph_dir = Path(os.getenv("CONCEPT_GRAPH_DIR", "data/concept_graphs"))
        self.max_upload_pages = int(os.getenv("MAX_UPLOAD_PAGES", "35"))
        self.max_upload_chunks = int(os.getenv("MAX_UPLOAD_CHUNKS", "90"))
        self.client = None
        self.retriever = None
        self.current_source: Optional[SourceInfo] = None
        self.current_chunks: list[dict] = []

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
                self.current_chunks = restored_chunks
                self.current_source = restored_source
                self.rag_source_file = restored_source.processed_path
                restored = self.retriever.index_chunks(restored_chunks)
                if restored:
                    preview = self.retriever.chunks[0] if self.retriever.chunks else {}
                    restored_source.chunk_count = len(self.retriever.chunks)
                    restored_source.preview_title = restored_source.preview_title or preview.get("title")
                    restored_source.preview_text = restored_source.preview_text or preview.get("text")
                    self.current_source = restored_source
                    self.rag_source_file = restored_source.processed_path

            if not restored:
                if restored_source and self.current_chunks:
                    print(
                        "AdaptiveTutorEngine: latest source restored without embeddings; "
                        "direct page/chapter lookup is available, semantic RAG may be limited.",
                        flush=True,
                    )
                else:
                    self.retriever.load_and_index_file(self.rag_source_file)
                    preview = self.retriever.chunks[0] if self.retriever and self.retriever.chunks else {}
                    self.current_chunks = self.retriever.chunks if self.retriever else []
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

    def build_heuristic_source_intelligence(self, source_id: str, file_name: str, pages: list[dict], chunks: list[dict]) -> dict:
        source_text = "\n".join(page.get("text", "") for page in pages[:6])
        detected_title = infer_title_from_pages(file_name, pages)
        subject = guess_subject_from_text(source_text, file_name)
        chapters_by_key: dict[str, dict] = {}
        concept_map: dict[str, dict] = {}

        for chunk in chunks:
            chapter_number = chunk.get("chapter_number")
            chapter_title = chunk.get("chapter_title")
            if chapter_number or chapter_title:
                key = f"{chapter_number or 'unknown'}:{chapter_title or ''}"
                chapter = chapters_by_key.setdefault(
                    key,
                    {
                        "chapter_number": chapter_number,
                        "title": chapter_title or f"Chapter {chapter_number}",
                        "pages": [],
                        "concepts": [],
                    },
                )
                if chunk.get("page_number") and chunk["page_number"] not in chapter["pages"]:
                    chapter["pages"].append(chunk["page_number"])

            for concept in chunk.get("concept_tags", [])[:4]:
                item = concept_map.setdefault(
                    concept,
                    {
                        "id": re.sub(r"[^a-z0-9]+", "-", concept.lower()).strip("-")[:60],
                        "name": concept,
                        "description": f"Concept detected from {chunk.get('title', 'the source')}.",
                        "source_refs": [],
                        "prerequisites": [],
                        "next_concepts": [],
                    },
                )
                ref = {
                    "title": chunk.get("title"),
                    "page_number": chunk.get("page_number"),
                    "chapter_number": chunk.get("chapter_number"),
                }
                if ref not in item["source_refs"]:
                    item["source_refs"].append(ref)

        concepts = list(concept_map.values())[:24]
        for index, concept in enumerate(concepts):
            if index > 0:
                concept["prerequisites"] = [concepts[index - 1]["name"]]
            if index + 1 < len(concepts):
                concept["next_concepts"] = [concepts[index + 1]["name"]]

        return {
            "source_id": source_id,
            "detected_title": detected_title,
            "subject": subject,
            "chapters": list(chapters_by_key.values()),
            "concepts": concepts,
            "generated_by": "heuristic",
            "heuristic_version": 2,
        }

    def generate_source_intelligence(self, source_id: str, file_name: str, pages: list[dict], chunks: list[dict]) -> dict:
        fallback = self.build_heuristic_source_intelligence(source_id, file_name, pages, chunks)
        if not self.client:
            return fallback

        source_outline = []
        for chunk in chunks[:30]:
            source_outline.append(
                {
                    "title": chunk.get("title"),
                    "page_number": chunk.get("page_number"),
                    "chapter_number": chunk.get("chapter_number"),
                    "chapter_title": chunk.get("chapter_title"),
                    "concept_tags": chunk.get("concept_tags", []),
                    "text_preview": (chunk.get("text", "") or "")[:900],
                }
            )

        prompt = (
            "Analyze this uploaded learning source for an adaptive tutoring app.\n"
            "Derive metadata and a concept graph only from the provided source previews. Do not invent concepts not supported by the source.\n"
            "Return strict JSON only with fields: detected_title, subject, chapters, concepts.\n"
            "chapters: array of {chapter_number, title, pages, concepts}.\n"
            "concepts: array of {id, name, description, source_refs, prerequisites, next_concepts}.\n"
            "Each source_ref must include title, page_number, and chapter_number when available.\n"
            "next_concepts should represent the most natural source-grounded concept to study next.\n\n"
            f"File name: {file_name}\n"
            f"Source chunks:\n{json.dumps(source_outline, ensure_ascii=False)[:12000]}"
        )

        try:
            from google.genai import types

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                config=types.GenerateContentConfig(
                    temperature=0.15,
                    response_mime_type="application/json",
                ),
            )
            parsed = self.parse_json_object(response.text or "")
            concepts = parsed.get("concepts") if isinstance(parsed.get("concepts"), list) else fallback["concepts"]
            chapters = parsed.get("chapters") if isinstance(parsed.get("chapters"), list) else fallback["chapters"]
            return {
                "source_id": source_id,
                "detected_title": str(parsed.get("detected_title") or fallback["detected_title"]),
                "subject": str(parsed.get("subject") or fallback["subject"]),
                "chapters": chapters,
                "concepts": concepts[:40],
                "generated_by": "gemini",
            }
        except Exception as exc:
            print(f"AdaptiveTutorEngine: source intelligence generation failed: {exc}", flush=True)
            return fallback

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
        self.concept_graph_dir.mkdir(parents=True, exist_ok=True)

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
        processed_chunks_path = self.processed_source_dir / f"{source_id}.chunks.json"
        processed_chunks_path.write_text(json.dumps(chunks, indent=2), encoding="utf-8")
        source_graph = self.generate_source_intelligence(source_id, safe_name, pages, chunks)
        concept_graph_path = self.concept_graph_dir / f"{source_id}.json"
        concept_graph_path.write_text(json.dumps(source_graph, indent=2), encoding="utf-8")

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
        self.current_chunks = chunks

        source = SourceInfo(
            source_id=source_id,
            file_name=safe_name,
            content_type=upload.content_type or "application/octet-stream",
            processed_path=str(processed_path),
            chunk_count=len(chunks),
            created_at=datetime.now(timezone.utc).isoformat(),
            preview_title=chunks[0]["title"],
            preview_text=chunks[0]["text"],
            detected_title=source_graph.get("detected_title"),
            subject=source_graph.get("subject"),
            chapters=source_graph.get("chapters", []),
            concept_count=len(source_graph.get("concepts", [])),
            concept_graph_path=str(concept_graph_path),
            processed_chunks_path=str(processed_chunks_path),
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
        material_title = self.display_material_title()
        subject = self.current_source.subject if self.current_source and self.current_source.subject else "Unknown subject"
        for index, source in enumerate(sources, start=1):
            page = f"page={source.get('page_number')}" if source.get("page_number") else "page=unknown"
            chapter = f"chapter={source.get('chapter_number')}" if source.get("chapter_number") else "chapter=unknown"
            blocks.append(
                f"[Source {index}: {material_title} | subject={subject} | {page} | {chapter} | chunk={source['title']} | relevance={source['score']:.3f}]\n"
                f"{source['text']}"
            )
        return "\n\n".join(blocks)

    def display_material_title(self) -> str:
        if not self.current_source:
            return "Uploaded source"

        detected = (self.current_source.detected_title or "").strip()
        file_stem = Path(self.current_source.file_name).stem.replace("_", " ").strip()
        if detected and "_" not in detected and detected.lower() != file_stem.lower():
            return detected

        # No hardcoded title fallbacks — fall through to infer_title_from_pages

        title = infer_title_from_pages(
            self.current_source.file_name,
            [
                {
                    "page_number": chunk.get("page_number"),
                    "text": re.sub(r"^Topic:\s*.+?\n", "", chunk.get("text", ""), flags=re.DOTALL),
                }
                for chunk in (self.current_chunks or [])[:8]
            ],
        )
        return title or file_stem or self.current_source.file_name

    def source_learning_map_context(self, limit: int = 10) -> str:
        graph = self.current_concept_graph()
        if not graph:
            return "No source learning map is available."

        concepts = graph.get("concepts", [])[:limit] if isinstance(graph.get("concepts"), list) else []
        concept_lines = []
        for concept in concepts:
            next_items = concept.get("next_concepts") if isinstance(concept.get("next_concepts"), list) else []
            prereqs = concept.get("prerequisites") if isinstance(concept.get("prerequisites"), list) else []
            concept_lines.append(
                f"- {concept.get('name')}: prereqs={prereqs[:2]}, next={next_items[:2]}"
            )

        return (
            f"Detected title: {self.display_material_title()}\n"
            f"Subject: {graph.get('subject') or 'Unknown'}\n"
            "Source-derived concepts:\n"
            + ("\n".join(concept_lines) if concept_lines else "(none)")
        )

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

    def requested_page_number(self, question: str) -> Optional[int]:
        patterns = [
            r"\bpage\s+(\d{1,4})\b",
            r"\bp\.?\s*(\d{1,4})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, question, flags=re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    def retrieve_page_sources(self, page_number: int, k: int = 4) -> list[dict]:
        chunks = self.current_chunks or (self.retriever.chunks if self.retriever else [])
        page_chunks = [
            dict(chunk)
            for chunk in chunks
            if chunk.get("page_number") == page_number
        ]
        for chunk in page_chunks:
            chunk["score"] = 1.0
        return page_chunks[:k]

    def retrieve_checked_sources(self, question: str) -> dict:
        page_number = self.requested_page_number(question)
        if page_number is not None:
            page_sources = self.retrieve_page_sources(page_number, k=self.rag_context_check_k + 1)
            if page_sources:
                return {
                    "sources": page_sources,
                    "status": "grounded_page",
                    "note": (
                        f"The student asked about page {page_number}, so the system retrieved that page directly. "
                        "A vague page-level request is answerable as an overview plus a clarifying learning check."
                    ),
                    "attempts": [
                        {
                            "query": f"page:{page_number}",
                            "answerable": True,
                            "reason": f"Direct page lookup found {len(page_sources)} chunk(s) for page {page_number}.",
                        }
                    ],
                }

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

    def classify_learning_state(self, payload: ChatRequest) -> str:
        message = payload.message.strip().lower()
        recent = payload.history[-5:]
        recent_students = [item.text.strip().lower() for item in recent if item.sender == "student"]
        recent_tutors = [item.text.strip().lower() for item in recent if item.sender == "tutor"]

        unsure_markers = [
            "i don't know",
            "i dont know",
            "idk",
            "not sure",
            "confused",
            "i'm lost",
            "im lost",
            "i don't get",
            "i dont get",
            "no idea",
        ]
        more_help_markers = [
            "explain more",
            "explain again",
            "simpler",
            "break it down",
            "i still don't",
            "i still dont",
            "just tell me",
            "give me the answer",
        ]
        confident_wrong_markers = [
            "obviously",
            "definitely",
            "it is always",
            "it must be",
            "i am sure",
            "i'm sure",
        ]
        follow_up_question_markers = [
            "about that",
            "about it",
            "that part",
            "this part",
            "why is that",
            "how so",
            "what about",
            "can you explain",
            "explain more",
        ]

        if not recent_students and not recent_tutors:
            return "new_topic"
        if any(marker in message for marker in unsure_markers):
            return "student_unsure"
        if any(marker in message for marker in more_help_markers):
            return "asking_for_more_help"
        if any(marker in message for marker in confident_wrong_markers):
            return "wrong_assumption"
        if "?" in message and recent_tutors and not any(marker in message for marker in follow_up_question_markers):
            return "new_topic"
        if len(message.split()) <= 8 and recent_tutors:
            return "partial_understanding"
        if "?" not in message and recent_tutors:
            return "partial_understanding"
        return "new_topic" if not recent_students else "partial_understanding"

    def is_follow_up_turn(self, payload: ChatRequest, learning_state: str) -> bool:
        if not payload.active_question:
            return False

        message = payload.message.strip().lower()
        active_question = payload.active_question.strip().lower()
        if not active_question or message == active_question:
            return False

        if learning_state in {
            "student_unsure",
            "wrong_assumption",
            "asking_for_more_help",
        }:
            return True
        if learning_state == "partial_understanding" and "?" not in message:
            return True

        follow_up_markers = [
            "why",
            "how",
            "what about",
            "explain",
            "simpler",
            "again",
            "more",
            "i think",
            "maybe",
        ]
        if any(marker in message for marker in follow_up_markers) and payload.history:
            return True

        return False

    def choose_hint_level(self, payload: ChatRequest, learning_state: str, is_follow_up: bool) -> tuple[int, bool]:
        current_level = max(1, min(4, payload.current_hint_level))

        if not payload.auto_hint:
            return current_level, False

        if not is_follow_up or learning_state == "new_topic":
            return 1, False
        if learning_state in {"student_unsure", "asking_for_more_help"}:
            next_level = min(current_level + 1, 4)
            return next_level, next_level < 4
        if learning_state == "wrong_assumption":
            next_level = min(max(current_level, 2) + 1, 4)
            return next_level, next_level < 4
        if learning_state == "partial_understanding":
            return max(current_level, 2), current_level < 3
        return current_level, current_level < 4

    def parse_quick_check_response(self, message: str) -> dict:
        if "quick check response" not in message.lower():
            return {"is_quick_check": False}

        question_match = re.search(r"Question:\s*(.+?)(?:\n|$)", message, flags=re.IGNORECASE | re.DOTALL)
        selected_match = re.search(r"Selected answer:\s*(.+?)(?:\n|$)", message, flags=re.IGNORECASE | re.DOTALL)
        correct_match = re.search(r"Correct:\s*(true|false)", message, flags=re.IGNORECASE)
        diagnostic_match = re.search(r"Diagnostic:\s*true", message, flags=re.IGNORECASE)
        correct_value = None
        if correct_match:
            correct_value = correct_match.group(1).lower() == "true"

        return {
            "is_quick_check": True,
            "question": re.sub(r"\s+", " ", question_match.group(1)).strip() if question_match else "",
            "selected_answer": re.sub(r"\s+", " ", selected_match.group(1)).strip() if selected_match else "",
            "is_correct": correct_value,
            "is_diagnostic": bool(diagnostic_match) or correct_value is None,
        }

    def choose_check_difficulty(
        self,
        payload: ChatRequest,
        learning_state: str,
        is_follow_up: bool,
        effective_hint_level: int,
    ) -> str:
        current = payload.current_check_difficulty if payload.current_check_difficulty in {
            "diagnostic",
            "easy",
            "medium",
            "hard",
        } else "diagnostic"
        order = ["diagnostic", "easy", "medium", "hard"]
        current_index = order.index(current)
        check = self.parse_quick_check_response(payload.message)

        if not is_follow_up or learning_state == "new_topic":
            return "diagnostic"
        if check.get("is_diagnostic"):
            return "easy"
        if check.get("is_correct") is True:
            return order[min(current_index + 1, len(order) - 1)]
        if check.get("is_correct") is False:
            return order[max(current_index - 1, 1)]
        if learning_state in {"student_unsure", "asking_for_more_help", "wrong_assumption"}:
            return order[max(current_index - 1, 1)]
        if effective_hint_level >= 4:
            return "hard"
        return current if current != "diagnostic" else "easy"

    def adjust_hint_for_evidence(self, payload: ChatRequest, proposed_hint_level: int, learning_state: str, is_follow_up: bool) -> tuple[int, bool]:
        current = max(1, min(4, payload.current_hint_level))
        proposed = max(1, min(4, proposed_hint_level))
        check = self.parse_quick_check_response(payload.message)

        if not is_follow_up or learning_state == "new_topic":
            return 1, False
        if check.get("is_diagnostic"):
            # Diagnostic response: stay at current level, let check_difficulty advance
            return current, False
        if check.get("is_correct") is True:
            # Correct answer: keep hint support steady; let check difficulty advance separately.
            return current, True
        if check.get("is_correct") is False:
            return min(current + 1, 4), True
        if learning_state in {"student_unsure", "asking_for_more_help"}:
            return min(current + 1, 4), True
        if learning_state == "wrong_assumption":
            return min(max(current, 2) + 1, 4), True
        return min(proposed, current + 1), False

    def fallback_turn_plan(self, payload: ChatRequest) -> dict:
        learning_state = self.classify_learning_state(payload)
        is_follow_up = self.is_follow_up_turn(payload, learning_state)
        active_question = payload.active_question if is_follow_up and payload.active_question else payload.message
        effective_hint_level, should_escalate_next = self.choose_hint_level(payload, learning_state, is_follow_up)
        effective_hint_level, should_escalate_next = self.adjust_hint_for_evidence(
            payload,
            effective_hint_level,
            learning_state,
            is_follow_up,
        )
        check_difficulty = self.choose_check_difficulty(payload, learning_state, is_follow_up, effective_hint_level)
        return {
            "learning_state": learning_state,
            "is_follow_up": is_follow_up,
            "active_question": active_question,
            "effective_hint_level": effective_hint_level,
            "should_escalate_next": should_escalate_next,
            "check_difficulty": check_difficulty,
            "planner_note": "Heuristic planner fallback used.",
        }

    def plan_conversation_turn(self, payload: ChatRequest) -> dict:
        if not self.client:
            return self.fallback_turn_plan(payload)

        print(
            f"AdaptiveTutorEngine: planning turn message={payload.message[:80]!r} "
            f"active_question={(payload.active_question or '')[:80]!r} "
            f"history_items={len(payload.history)}",
            flush=True,
        )
        recent_history = payload.history[-10:]
        history_text = "\n".join(
            f"{item.sender}: {item.text}" for item in recent_history
        )
        current_level = max(1, min(4, payload.current_hint_level))
        current_difficulty = payload.current_check_difficulty if payload.current_check_difficulty in {
            "diagnostic",
            "easy",
            "medium",
            "hard",
        } else "diagnostic"
        prompt = (
            "You are planning the next turn for a source-grounded tutoring chat.\n"
            "Use the recent conversation to decide whether the student message is a follow-up to the active question or a fresh question.\n"
            "Separate two ideas clearly: hint level means how much support the student needs; check difficulty means how challenging the next question should be.\n"
            "Important rules:\n"
            "- If the student says they do not know, gives a short answer, or answers a quick-check option, treat it as a follow-up when there is an active question.\n"
            "- If it is a follow-up, keep the active_question as the original learning question. Do not make the short reply the retrieval query.\n"
            "- If the student asks a clearly new topic question, reset to that question and start at level 1.\n"
            "- Escalate by at most one level. Do not use level 4 for a brand-new topic.\n"
            "- Level 4 is only for repeated confusion, a direct request for the answer after scaffolding, or a need to resolve the concept.\n"
            "- A correct quick-check answer should usually increase check difficulty, not hint level.\n"
            "- A diagnostic quick-check answer only tells where to begin; it should not increase hint level.\n"
            "- Increase hint level only when the student is uncertain, asks for more help, gives a wrong answer, or shows a wrong assumption.\n\n"
            f"Current active_question: {payload.active_question or '(none)'}\n"
            f"Current hint level: {current_level}\n"
            f"Current check difficulty: {current_difficulty}\n"
            f"Recent conversation:\n{history_text or '(none)'}\n\n"
            f"Current student message:\n{payload.message}\n\n"
            "Return strict JSON only with fields: "
            "is_follow_up, active_question, learning_state, recommended_hint_level, recommended_check_difficulty, should_escalate_next, reason. "
            "learning_state must be one of: new_topic, student_unsure, partial_understanding, wrong_assumption, "
            "asking_for_more_help, ready_for_full_explanation. "
            "recommended_check_difficulty must be one of: diagnostic, easy, medium, hard."
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
            print(f"AdaptiveTutorEngine: planner raw result={parsed}", flush=True)
            allowed_states = {
                "new_topic",
                "student_unsure",
                "partial_understanding",
                "wrong_assumption",
                "asking_for_more_help",
                "ready_for_full_explanation",
            }
            learning_state = parsed.get("learning_state")
            if learning_state not in allowed_states:
                raise ValueError("planner returned invalid learning_state")

            is_follow_up = bool(parsed.get("is_follow_up"))
            active_question = str(parsed.get("active_question") or "").strip()
            if not active_question:
                active_question = payload.active_question if is_follow_up and payload.active_question else payload.message

            recommended = int(parsed.get("recommended_hint_level") or current_level)
            recommended = max(1, min(4, recommended))
            if not is_follow_up or learning_state == "new_topic":
                recommended = 1
                active_question = payload.message
                is_follow_up = False
            elif recommended > current_level + 1:
                recommended = current_level + 1

            if recommended == 4 and (not is_follow_up or current_level < 3):
                recommended = min(3, max(1, current_level + 1))

            recommended, evidence_should_escalate = self.adjust_hint_for_evidence(
                payload,
                recommended,
                learning_state,
                is_follow_up,
            )
            check_difficulty = str(parsed.get("recommended_check_difficulty") or "").strip()
            if check_difficulty not in {"diagnostic", "easy", "medium", "hard"}:
                check_difficulty = self.choose_check_difficulty(payload, learning_state, is_follow_up, recommended)
            else:
                check_difficulty = self.choose_check_difficulty(payload, learning_state, is_follow_up, recommended)

            planner_should_escalate = bool(parsed.get("should_escalate_next"))
            should_escalate_next = evidence_should_escalate or (
                planner_should_escalate
                and learning_state in {"student_unsure", "asking_for_more_help", "wrong_assumption"}
            )
            return {
                "learning_state": learning_state,
                "is_follow_up": is_follow_up,
                "active_question": active_question,
                "effective_hint_level": recommended,
                "should_escalate_next": should_escalate_next and recommended < 4,
                "check_difficulty": check_difficulty,
                "planner_note": str(parsed.get("reason") or "AI planner used.").strip(),
            }
        except Exception as exc:
            print(f"AdaptiveTutorEngine: turn planner error: {exc}", flush=True)
            return self.fallback_turn_plan(payload)

    def learning_state_note(self, learning_state: str, hint_level: int) -> str:
        notes = {
            "new_topic": "New topic detected; starting with a low-pressure orientation prompt.",
            "student_unsure": "Student appears unsure; increasing support by one step.",
            "partial_understanding": "Student has attempted an idea; giving targeted guidance.",
            "wrong_assumption": "Student may be confident but off-track; surfacing the contradiction gently.",
            "asking_for_more_help": "Student asked for more help; increasing support by one step.",
            "ready_for_full_explanation": "Student is ready for a complete explanation after scaffolding.",
        }
        return f"{notes.get(learning_state, 'Continuing the current scaffold.')} Active hint level: {hint_level}/4."

    def build_socratic_instruction(
        self,
        language: str,
        mode: str,
        hint_level: int,
        learning_state: str,
        check_difficulty: str,
    ) -> str:
        strategy = HINT_STRATEGIES.get(hint_level, "orient")
        base = (
            "You are a warm, conversational tutor for university students. "
            "Use simple words. Do not sound like a rigid worksheet. "
            "Teach before you test. Every response must begin with a plain-language explanation grounded in the source. "
            "Do not open with a question and do not assume the student has already read the page. "
            "After the explanation, ask at most one short question or attach one short objective check if it helps confirm understanding. "
            "Do not pressure the student or ask for a long answer. "
            "Use the retrieved source as ground truth and cite the source title when you use it. "
            "If the student asks about a whole page or chapter without naming a specific concept, explain the central idea of that page/chapter first, then use one short question to locate the confusing part. "
            "Use the source learning map to notice prerequisite concepts. If the student likely needs a foundation first, explain that foundation before asking a diagnostic question. "
            "Make quick_check difficulty match the provided check_difficulty. Diagnostic checks identify the student's starting point and should not have a correct_index. Easy checks ask recognition questions. Medium checks ask connection/application questions. Hard checks ask transfer, explanation, or source-evidence questions. "
            "If check_difficulty is easy, medium, or hard, do not ask another 'which part is unclear' diagnostic question. Teach the selected focus and check understanding of that focus. "
            "Return strict JSON only with fields: text, quick_check. "
            "quick_check may be null, or an object with: prompt, options, correct_index, explanation. "
            "correct_index must be zero-based. Use 2 to 4 options only. "
            "If quick_check is provided, the quick_check.prompt must be the exact question the student is answering. "
            "Do not put a different question in text. Text should only prepare the student for that same quick_check prompt. "
            "When you include quick_check, keep text to 1 or 2 setup sentences and do not end text with a question. "
        )

        level_rules = {
            1: (
                "Hint level 1 strategy: orient. Do not give a full answer or solve the whole concept. "
                "For a specific page/chapter request, give a very short page/chapter overview from the source first, in plain language. "
                "Then ask one source-specific diagnostic question that checks the student's foundation or helps identify the confusing part. "
                "Keep it to 2 or 3 short sentences and make sure the explanation comes before the question. "
                "Avoid the exact phrase 'what do you already know'. "
                "Do not use generic choices like 'what it means, why it matters, or how it works' unless those choices are tied to actual source content."
            ),
            2: (
                "Hint level 2 strategy: narrow. Do not give the full answer. "
                "Keep it to 2 or 3 short sentences. Point to the most useful part of the source, explain it plainly, and ask a concrete, low-pressure question about it."
            ),
            3: (
                "Hint level 3 strategy: similar_example. Give a simple analogy or nearby example, but do not simply dump the final answer. "
                "Keep the example short. The student should still have a small thinking step left. "
                "Start with a short explanation of the source idea, then use the example. "
                "Include a quick_check with objective options if it would reduce typing burden."
            ),
            4: (
                "Hint level 4 strategy: full_reasoning. Give the full source-grounded explanation with clear reasoning. "
                "Include a quick_check with objective options or a very short own-words check."
            ),
        }

        mode_instructions = {
            "analogy": "Prefer analogy-style phrasing when useful.",
            "step-step": "Prefer clear step-by-step phrasing when useful.",
            "visual": "Prefer visual or spatial phrasing when useful.",
            "peer": "Use a friendly peer-study tone.",
        }

        return (
            base
            + level_rules.get(hint_level, level_rules[1])
            + " "
            + mode_instructions.get(mode, mode_instructions["step-step"])
            + f" Student state classification: {learning_state}. "
            + f" Check difficulty: {check_difficulty}. "
            + f" Reply in the language matching this code: {language}. "
            + "(EN = English, FR = French, SW = Swahili, HA = Hausa, YO = Yoruba). "
            + f"The hint_strategy is {strategy}."
        )

    def teaching_brief(self, sources: list, learning_direction: dict, student_focus: str = "") -> str:
        source = sources[0] if sources else {}
        summary = self.source_summary(source) if source else {
            "title": self.display_material_title(),
            "core": "the closest available idea in the uploaded source",
            "steps": [],
            "why": "The explanation must stay close to the uploaded material.",
        }
        current = learning_direction.get("current_concept") or {}
        prerequisite = learning_direction.get("prerequisite_gap")
        next_concept = learning_direction.get("next_concept") or {}

        current_name = str(current.get("name") or "").strip()
        prereq_name = ""
        if isinstance(prerequisite, str):
            prereq_name = prerequisite.strip()
        elif isinstance(prerequisite, dict):
            prereq_name = str(prerequisite.get("name") or "").strip()
        next_name = str(next_concept.get("name") or "").strip()

        lines = [
            f"Source title: {summary['title']}",
            f"Core idea from the source: {summary['core']}",
        ]
        if summary.get("steps"):
            first_steps = [str(step).strip() for step in summary["steps"][:2] if str(step).strip()]
            if first_steps:
                lines.append("Helpful source details: " + " ".join(first_steps))
        if current_name:
            lines.append(f"Current concept label: {current_name}")
        if prereq_name:
            lines.append(f"Likely prerequisite: {prereq_name}")
        if next_name:
            lines.append(f"Likely next concept: {next_name}")
        if student_focus:
            lines.append(f"Student selected focus: {student_focus}")
            lines.append("Next required action: teach this selected focus first, then ask a non-diagnostic check.")
        lines.append(
            "Instruction: explain the core idea in plain language first. Do not assume the student already read the page. "
            "Only after that, ask one short check or attach one objective quick_check."
        )
        return "\n".join(lines)

    def looks_question_led(self, text: str) -> bool:
        stripped = re.sub(r"\s+", " ", text.strip().lower())
        if not stripped:
            return True
        question_starts = (
            "to help me",
            "could you",
            "can you",
            "before we go deeper",
            "let's check",
            "which part",
            "what part",
            "do you",
        )
        return stripped.startswith(question_starts) or stripped.count("?") > 1

    def reinforce_teaching_first(self, text: str, sources: list, learning_direction: dict, hint_level: int) -> str:
        if hint_level > 2 or not sources:
            return text.strip()

        source = sources[0] if sources else {}
        summary = self.source_summary(source) if source else {
            "title": self.display_material_title(),
            "core": "the closest available idea in the uploaded source",
            "steps": [],
            "why": "The explanation must stay close to the uploaded material.",
        }
        if not self.looks_question_led(text) and len(text.strip()) >= 160:
            return text.strip()

        prefix = f"Using {summary['title']}, the main idea is {summary['core']}."
        if summary.get("steps"):
            first_step = str(summary["steps"][0]).strip()
            if first_step:
                prefix += f" A helpful detail from the source is: {first_step}"
        if not text.strip():
            return prefix
        if text.strip().startswith(prefix):
            return text.strip()
        return f"{prefix}\n\n{text.strip()}"

    def split_trailing_question(self, text: str) -> tuple[str, Optional[str]]:
        clean = text.strip()
        if "?" not in clean:
            return clean, None

        match = re.search(r"([^.\n!?]*\?)(?:\s*)$", clean, flags=re.DOTALL)
        if not match:
            return clean, None

        question = re.sub(r"\s+", " ", match.group(1)).strip()
        body = clean[: match.start(1)].strip()
        return body, question

    def diagnostic_options_for_prompt(self, prompt: str, sources: list, payload: ChatRequest, check_difficulty: str) -> Optional[list[str]]:
        direction = self.build_learning_direction(
            payload.active_question or payload.message,
            sources,
            "student_unsure",
            check_difficulty,
        )
        current = direction.get("current_concept") or {}
        next_concept = direction.get("next_concept") or {}
        prereq = direction.get("prerequisite_gap")

        current_name = str(current.get("name") or "").strip()
        next_name = str(next_concept.get("name") or "").strip()
        prereq_name = ""
        if isinstance(prereq, str):
            prereq_name = prereq.strip()
        elif isinstance(prereq, dict):
            prereq_name = str(prereq.get("name") or "").strip()

        prompt_lower = prompt.lower()
        prompt_mentions_current = bool(current_name and current_name.lower() in prompt_lower)

        if check_difficulty == "diagnostic":
            if prompt_mentions_current:
                options = [current_name]
                if prereq_name:
                    options.append(prereq_name)
                if next_name:
                    options.append(next_name)
                return options[:3]
            return None

        options = []
        if check_difficulty == "easy":
            if current_name:
                options.append(current_name)
            if prereq_name and prereq_name not in options:
                options.append(prereq_name)
            if next_name and next_name not in options:
                options.append(next_name)
            if len(options) >= 2:
                return options[:3]

        if check_difficulty == "medium":
            if current_name:
                options.append(f"Apply {current_name} to this page")
            if prereq_name:
                options.append(f"Go back to {prereq_name} first")
            if next_name:
                options.append(f"Use {next_name} as the next step")
            if len(options) >= 2:
                return options[:3]

        if check_difficulty == "hard":
            if current_name:
                options.append(f"Explain {current_name} using evidence from the source")
            if next_name:
                options.append(f"Connect it to {next_name}")
            if prereq_name:
                options.append(f"Show why {prereq_name} matters here")
            if len(options) >= 2:
                return options[:3]

        return None

    def clean_concept_label(self, value: str) -> str:
        label = re.sub(r"\s+", " ", str(value or "")).strip()
        label = re.sub(
            r"^(the\s+)?(phrase or idea|prerequisite idea|follow-on idea|next idea|core concept)\s*:\s*",
            "",
            label,
            flags=re.IGNORECASE,
        ).strip()
        return label

    def concept_by_label(self, label: str, learning_direction: dict) -> dict:
        clean_label = self.clean_concept_label(label).lower()
        candidates = []
        for key in ("current_concept", "next_concept"):
            concept = learning_direction.get(key)
            if isinstance(concept, dict):
                candidates.append(concept)
        prereq = learning_direction.get("prerequisite_gap")
        if isinstance(prereq, dict):
            candidates.append(prereq)

        graph = self.current_concept_graph()
        graph_concepts = graph.get("concepts", []) if isinstance(graph, dict) else []
        candidates.extend([concept for concept in graph_concepts if isinstance(concept, dict)])

        for concept in candidates:
            name = self.clean_concept_label(str(concept.get("name") or ""))
            concept_id = self.clean_concept_label(str(concept.get("id") or "")).replace("_", " ")
            if clean_label and clean_label in {name.lower(), concept_id.lower()}:
                return concept
        return {}

    def fallback_quick_check(
        self,
        sources: list,
        learning_direction: dict,
        check_difficulty: str,
        student_focus: str = "",
    ) -> Optional[dict]:
        if check_difficulty == "diagnostic" or not sources:
            return None

        current = learning_direction.get("current_concept") or {}
        next_concept = learning_direction.get("next_concept") or {}
        current_name = self.clean_concept_label(student_focus) or self.clean_concept_label(str(current.get("name") or "")) or "the main idea"
        next_name = str(next_concept.get("name") or "").strip()
        selected_concept = self.concept_by_label(current_name, learning_direction) or current
        concept_description = str(selected_concept.get("description") or "").strip()
        summary = self.source_summary(sources[0])
        source_hint = summary.get("core") or "the explanation in the uploaded source"

        if check_difficulty == "easy":
            options = [
                concept_description or f"It is the main idea the source is explaining about {current_name}",
                "It is unrelated to what the source is explaining",
                "It is only a word to memorize, not an idea to understand",
            ]
            prompt = f"In this source, what does {current_name} mean?"
            return {
                "prompt": prompt,
                "options": options,
                "correct_index": 0,
                "explanation": f"The strongest option should connect back to the source idea: {source_hint}",
            }

        if check_difficulty == "medium":
            prompt = f"How does {current_name} connect to the main idea in this source?"
            options = [
                f"It helps explain the source's larger idea: {source_hint}",
                "It is a separate idea that does not affect understanding",
                "It only matters if the student memorizes the exact wording",
            ]
            return {
                "prompt": prompt,
                "options": options,
                "correct_index": 0,
                "explanation": "The best answer connects the selected concept back to the source's explanation, not just the wording.",
            }

        prompt = f"Which answer uses the source best to explain {current_name}?"
        options = [
            f"{current_name} matters because it helps explain the source's larger idea.",
            f"{current_name} matters because it avoids using the source.",
            f"{current_name} matters only because the term appears on the page.",
        ]
        if next_name:
            options[0] = f"{current_name} matters because it leads into {next_name}, the next idea in the source."
        return {
            "prompt": prompt,
            "options": options,
            "correct_index": 0,
            "explanation": "The strongest answer connects the concept back to source-grounded scientific study.",
        }

    def align_quick_check_with_response(
        self,
        text: str,
        quick_check: Optional[dict],
        hint_level: int,
        sources: list,
        payload: ChatRequest,
        check_difficulty: str,
    ) -> tuple[str, Optional[dict]]:
        if not isinstance(quick_check, dict):
            return text, None

        body, response_question = self.split_trailing_question(text)
        if response_question:
            quick_check["prompt"] = response_question
            text = body or "Let's check the source with one quick question."

        prompt = str(quick_check.get("prompt") or "").strip()
        if not prompt:
            return text, None

        if "?" in text:
            text, _ignored = self.split_trailing_question(text)
            text = text or "Let's check the source with one quick question."

        quick_check["prompt"] = prompt
        if check_difficulty == "diagnostic":
            diagnostic_options = self.diagnostic_options_for_prompt(prompt, sources, payload, check_difficulty)
            if diagnostic_options:
                quick_check["options"] = diagnostic_options
                quick_check.pop("correct_index", None)
                quick_check["explanation"] = "No single option is wrong here. Your choice tells the tutor where to start."
            return text.strip(), quick_check

        diagnostic_phrases = (
            "which part feels unclear",
            "where you are starting from",
            "what feels unclear",
            "which part is confusing",
            "before we go deeper",
        )
        if any(phrase in prompt.lower() for phrase in diagnostic_phrases):
            return text.strip(), None

        correct_index = quick_check.get("correct_index")
        options = quick_check.get("options")
        if not isinstance(correct_index, int) or not isinstance(options, list) or not (0 <= correct_index < len(options)):
            return text.strip(), None

        return text.strip(), quick_check

    def generate_socratic_response(
        self,
        payload: ChatRequest,
        sources: list,
        hint_level: int,
        learning_state: str,
        check_difficulty: str,
        learning_direction: dict,
    ) -> dict:
        source_context = self.build_source_context(sources)
        learning_map_context = self.source_learning_map_context(limit=12)
        print(
            f"AdaptiveTutorEngine: generating socratic response hint_level={hint_level} "
            f"learning_state={learning_state} sources={len(sources)}",
            flush=True,
        )
        history_text = "\n".join(
            f"{item.sender}: {item.text}" for item in payload.history[-5:]
        )
        check_evidence = self.parse_quick_check_response(payload.message)
        student_focus = check_evidence.get("selected_answer", "") if check_evidence.get("is_quick_check") else ""
        prompt = (
            "Recent conversation:\n"
            f"{history_text or '(no previous turns)'}\n\n"
            f"Active learning question:\n{payload.active_question or payload.message}\n\n"
            "Teaching brief:\n"
            f"{self.teaching_brief(sources, learning_direction, student_focus)}\n\n"
            "Source learning map:\n"
            f"{learning_map_context[:3000]}\n\n"
            "Structured learning direction:\n"
            f"{json.dumps(learning_direction, ensure_ascii=False)[:2500]}\n\n"
            "Retrieved source context:\n"
            f"{source_context[:7000]}\n\n"
            "Student message:\n"
            f"{payload.message}\n\n"
            "Create the next tutor response for the requested hint level. "
            "Remember: the goal is understanding, not rushing to the final answer."
        )

        try:
            from google.genai import types

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                config=types.GenerateContentConfig(
                    system_instruction=self.build_socratic_instruction(
                        payload.language,
                        payload.mode,
                        hint_level,
                        learning_state,
                        check_difficulty,
                    ),
                    temperature=0.35,
                    response_mime_type="application/json",
                ),
            )
            parsed = self.parse_json_object(response.text or "")
            print(
                f"AdaptiveTutorEngine: socratic response received text_chars={len(str(parsed.get('text') or ''))} "
                f"has_quick_check={isinstance(parsed.get('quick_check'), dict)}",
                flush=True,
            )
            text = str(parsed.get("text") or "").strip()
            quick_check = parsed.get("quick_check")

            if not text:
                text = self.fallback_reply(payload.message, sources, payload.mode)
            else:
                text = self.reinforce_teaching_first(text, sources, learning_direction, hint_level)
            if hint_level == 1:
                text = self.ensure_level_one_diagnostic(text, sources)

            if not isinstance(quick_check, dict):
                quick_check = None
            else:
                options = quick_check.get("options")
                if not isinstance(options, list) or not 2 <= len(options) <= 4:
                    quick_check = None
                else:
                    text, quick_check = self.align_quick_check_with_response(
                        text,
                        quick_check,
                        hint_level,
                        sources,
                        payload,
                        check_difficulty,
                    )
            if quick_check is None and check_difficulty != "diagnostic":
                quick_check = self.fallback_quick_check(
                    sources,
                    learning_direction,
                    check_difficulty,
                    student_focus,
                )

            return {"text": text, "quick_check": quick_check}
        except Exception as exc:
            print(f"AdaptiveTutorEngine: Socratic response error: {exc}", flush=True)
            return {
                "text": (
                    self.orienting_fallback(payload.message, sources)
                    if hint_level == 1
                    else self.fallback_reply(payload.message, sources, payload.mode)
                ),
                "quick_check": None,
            }

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
            "I could not find enough support for this question in the uploaded source, "
            "so this is a general explanation rather than a source-grounded answer.\n\n"
        )

        if not self.client:
            return (
                prefix +
                "I cannot generate a general explanation right now because the chat model is unavailable. "
                f"Your question was: {question}"
            )

        try:
            from google.genai import types

            print(f"AdaptiveTutorEngine: generating general fallback question={question[:80]!r}", flush=True)
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
            print(f"AdaptiveTutorEngine: general fallback error: {exc}", flush=True)
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

    def orienting_fallback(self, prompt: str, sources: list) -> str:
        if not sources:
            return (
                "I could not find a strong source match yet. Which page, chapter, or concept should we focus on?"
            )

        source = sources[0]
        material_title = self.display_material_title()
        page = f"page {source.get('page_number')}" if source.get("page_number") else "this section"
        body = re.sub(r"^Topic:\s*.+?\n", "", source.get("text", ""), flags=re.DOTALL).strip()
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", body) if part.strip()]
        overview = " ".join(sentences[:2]) if sentences else "This section introduces the closest matching idea from the source."
        return (
            f"In {material_title}, {page} seems to be introducing this idea: {overview[:320]} "
            "Before we go deeper, which part feels unclear: the main idea, one word in the passage, or how the ideas connect?"
        )

    def ensure_level_one_diagnostic(self, text: str, sources: list) -> str:
        if "?" in text:
            return text

        source_prompt = self.current_source.detected_title if self.current_source and self.current_source.detected_title else self.current_source.file_name if self.current_source else ""
        direction = self.build_learning_direction(
            source_prompt,
            sources,
            "student_unsure",
            "diagnostic",
        )
        current = direction.get("current_concept") or {}
        next_concept = direction.get("next_concept") or {}
        prereq = direction.get("prerequisite_gap")
        current_name = str(current.get("name") or "").strip()
        next_name = str(next_concept.get("name") or "").strip()
        prereq_name = ""
        if isinstance(prereq, str):
            prereq_name = prereq.strip()
        elif isinstance(prereq, dict):
            prereq_name = str(prereq.get("name") or "").strip()

        pieces = []
        if current_name:
            pieces.append(f"the idea of {current_name}")
        if prereq_name:
            pieces.append(f"the prerequisite {prereq_name}")
        if next_name:
            pieces.append(f"the next idea {next_name}")

        if len(pieces) >= 2:
            question = "Before we go deeper, which part feels unclear: " + ", ".join(pieces[:-1]) + ", or " + pieces[-1] + "?"
        elif pieces:
            question = f"Before we go deeper, which part feels unclear: {pieces[0]}?"
        else:
            question = "Before we go deeper, which part feels unclear?"

        return f"{text.rstrip()}\n\n{question}"
    def fallback_reply(self, prompt: str, sources: list, mode: str = "step-step") -> str:
        if sources:
            return self.synthesize_fallback(prompt, sources[0], mode)

        return (
            "I could not find a strong match in the currently indexed source file. "
            "This may mean the question is outside the uploaded material, or the RAG threshold/chunking needs adjustment. "
            f"Your question was: {prompt}"
        )

    def current_concept_graph(self) -> dict:
        if not self.current_source:
            return {}
        existing = read_json_file(self.current_source.concept_graph_path, {})
        if existing and existing.get("generated_by") != "heuristic":
            return existing
        if existing and existing.get("heuristic_version") == 2:
            return existing
        chunks = self.current_chunks or (self.retriever.chunks if self.retriever else [])
        if not chunks:
            return {}

        chunks = [dict(chunk) for chunk in chunks]
        pages = [
            {
                "page_number": chunk.get("page_number"),
                "text": re.sub(r"^Topic:\s*.+?\n", "", chunk.get("text", ""), flags=re.DOTALL),
            }
            for chunk in chunks
        ]
        graph = self.build_heuristic_source_intelligence(
            self.current_source.source_id,
            self.current_source.file_name,
            pages,
            chunks,
        )
        graph["heuristic_version"] = 2
        self.concept_graph_dir.mkdir(parents=True, exist_ok=True)
        concept_graph_path = self.concept_graph_dir / f"{self.current_source.source_id}.json"
        concept_graph_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
        self.current_source.concept_graph_path = str(concept_graph_path)
        self.current_source.detected_title = self.current_source.detected_title or graph.get("detected_title")
        self.current_source.subject = self.current_source.subject or graph.get("subject")
        self.current_source.chapters = self.current_source.chapters or graph.get("chapters", [])
        self.current_source.concept_count = self.current_source.concept_count or len(graph.get("concepts", []))
        return graph

    def choose_source_grounded_next_concept(self, active_question: str, sources: list) -> Optional[dict]:
        graph = self.current_concept_graph()
        concepts = graph.get("concepts", []) if isinstance(graph, dict) else []
        if not concepts:
            return None

        text = " ".join(
            [
                active_question.lower(),
                " ".join(str(source.get("title", "")).lower() for source in sources),
                " ".join(str(source.get("text", "")[:500]).lower() for source in sources),
            ]
        )

        scored = []
        for index, concept in enumerate(concepts):
            name = str(concept.get("name") or "")
            description = str(concept.get("description") or "")
            score = 0
            for token in re.findall(r"[a-z0-9]{4,}", f"{name} {description}".lower()):
                if token in text:
                    score += 1
            scored.append((score, index, concept))

        scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        current = scored[0][2] if scored else concepts[0]
        next_names = current.get("next_concepts") if isinstance(current.get("next_concepts"), list) else []
        for next_name in next_names:
            for concept in concepts:
                if str(concept.get("name", "")).lower() == str(next_name).lower():
                    return concept

        current_index = concepts.index(current) if current in concepts else 0
        if current_index + 1 < len(concepts):
            return concepts[current_index + 1]
        return None

    def source_concept_for_question(self, active_question: str, sources: list) -> Optional[dict]:
        graph = self.current_concept_graph()
        concepts = graph.get("concepts", []) if isinstance(graph, dict) else []
        if not concepts:
            return None

        text = " ".join(
            [
                active_question.lower(),
                " ".join(str(source.get("title", "")).lower() for source in sources),
                " ".join(str(source.get("text", "")[:700]).lower() for source in sources),
            ]
        )
        scored = []
        for index, concept in enumerate(concepts):
            name = str(concept.get("name") or "")
            description = str(concept.get("description") or "")
            tokens = set(re.findall(r"[a-z0-9]{4,}", f"{name} {description}".lower()))
            score = sum(1 for token in tokens if token in text)
            scored.append((score, -index, concept))
        scored.sort(reverse=True)
        return scored[0][2] if scored and scored[0][0] > 0 else None

    def build_learning_direction(self, active_question: str, sources: list, learning_state: str, check_difficulty: str) -> dict:
        current = self.source_concept_for_question(active_question, sources)
        next_concept = self.choose_source_grounded_next_concept(active_question, sources)
        prerequisites = current.get("prerequisites", []) if isinstance(current, dict) and isinstance(current.get("prerequisites"), list) else []
        prerequisite_gap = prerequisites[0] if learning_state in {"student_unsure", "wrong_assumption", "asking_for_more_help"} and prerequisites else None

        return {
            "current_concept": current,
            "prerequisite_gap": prerequisite_gap,
            "next_concept": next_concept,
            "check_difficulty": check_difficulty,
            "reason": (
                "Derived from the uploaded source concept graph and the student's current response evidence."
                if current or next_concept
                else "No source concept match was strong enough for this turn."
            ),
        }

    def build_session_outcome(
        self,
        payload: ChatRequest,
        turn_plan: dict,
        effective_hint_level: int,
        socratic: dict,
        sources: list,
        retrieval_question: str,
    ) -> dict:
        message_lower = payload.message.lower()
        planner_note = str(turn_plan.get("planner_note", "")).lower()
        completed = (
            effective_hint_level >= 4
            and "quick check response" in message_lower
            and ("correct" in message_lower or "understanding" in planner_note or "complete" in planner_note)
        )
        next_concept = self.choose_source_grounded_next_concept(retrieval_question, sources) if completed else None
        confidence_score = 0.86 if completed else 0.0
        if completed and "correct: true" in message_lower:
            confidence_score = 0.92

        mastered_concept = retrieval_question if completed else None
        evidence = []
        if completed:
            evidence = [
                "Student completed the highest support level.",
                "Student answered a source-grounded quick check.",
                f"Planner note: {turn_plan.get('planner_note', '')}",
            ]

        return {
            "completed": completed,
            "confidence_score": confidence_score,
            "mastered_concept": mastered_concept,
            "evidence": evidence,
            "suggested_next_concept": next_concept,
            "reason": (
                "Suggested next concept is derived from the uploaded source concept graph."
                if next_concept
                else "No source-grounded next concept is available yet."
            ),
        }

    def chat(self, payload: ChatRequest) -> dict:
        request_id = uuid.uuid4().hex[:8]
        print(
            f"AdaptiveTutorEngine[{request_id}]: chat start message={payload.message[:100]!r} "
            f"hint={payload.current_hint_level} active_question={(payload.active_question or '')[:100]!r}",
            flush=True,
        )
        turn_plan = self.plan_conversation_turn(payload)
        print(f"AdaptiveTutorEngine[{request_id}]: turn_plan={turn_plan}", flush=True)
        learning_state = turn_plan["learning_state"]
        is_follow_up = turn_plan["is_follow_up"]
        # clean_active_question is what the frontend/planner sees next turn — always the
        # original question, never polluted with diagnostic metadata or selected answers.
        clean_active_question = turn_plan["active_question"] if is_follow_up else payload.message

        if is_follow_up:
            active_q = turn_plan["active_question"]
            current_msg = payload.message.strip()
            # retrieval_question is richer: combines active question + student's answer
            # so the semantic search evolves — but NEVER echoed back to the frontend.
            msg_clean = re.sub(r"^quick check response\..*?\n", "", current_msg, flags=re.IGNORECASE | re.DOTALL).strip()
            # Strip structured fields that come from the quick-check submission format
            msg_clean = re.sub(r"(Question|Selected answer|Correct|Diagnostic):\s*[^\n]*", "", msg_clean, flags=re.IGNORECASE).strip()
            if msg_clean and msg_clean.lower() not in {"none", "skip", ""}:
                retrieval_question = f"{active_q} {msg_clean}"
            else:
                retrieval_question = active_q
        else:
            retrieval_question = payload.message

        print(f"AdaptiveTutorEngine[{request_id}]: retrieval question={retrieval_question[:120]!r}", flush=True)
        retrieval = self.retrieve_checked_sources(retrieval_question)
        print(
            f"AdaptiveTutorEngine[{request_id}]: retrieval status={retrieval['status']} "
            f"attempts={retrieval['attempts']} sources={len(retrieval['sources'])}",
            flush=True,
        )
        grounded_statuses = {"grounded", "grounded_after_retry", "grounded_page"}
        sources = retrieval["sources"] if retrieval["status"] in grounded_statuses else []
        candidate_sources = retrieval["sources"]
        effective_hint_level = turn_plan["effective_hint_level"]
        should_escalate_next = turn_plan["should_escalate_next"]
        check_difficulty = turn_plan.get("check_difficulty") or self.choose_check_difficulty(
            payload,
            learning_state,
            is_follow_up,
            effective_hint_level,
        )
        hint_strategy = HINT_STRATEGIES.get(effective_hint_level, "orient")
        state_note = (
            f"{self.learning_state_note(learning_state, effective_hint_level)} "
            f"Planner: {turn_plan.get('planner_note', '')}"
        ).strip()
        # Pass the CLEAN active question to the response generator (not the enriched retrieval query)
        response_payload = payload.model_copy(update={"active_question": clean_active_question})

        learning_direction = self.build_learning_direction(
            retrieval_question,
            sources or candidate_sources,
            learning_state,
            check_difficulty,
        )

        if not self.client:
            print(f"AdaptiveTutorEngine[{request_id}]: returning no-client fallback", flush=True)
            return {
                "text": self.fallback_reply(payload.message, sources, payload.mode),
                "sources": sources,
                "candidate_sources": candidate_sources,
                "grounding_status": retrieval["status"],
                "retrieval_note": retrieval["note"],
                "retrieval_attempts": retrieval["attempts"],
                "effective_hint_level": effective_hint_level,
                "hint_strategy": hint_strategy,
                "should_escalate_next": should_escalate_next,
                "learning_state_note": state_note,
                "check_difficulty": check_difficulty,
                "learning_direction": learning_direction,
                "active_question": clean_active_question,
                "is_follow_up": is_follow_up,
                "quick_check": None,
                "session_outcome": {
                    "completed": False,
                    "confidence_score": 0.0,
                    "mastered_concept": None,
                    "evidence": [],
                    "suggested_next_concept": None,
                    "reason": "No chat model was available.",
                },
                "warning": "Demo fallback active because Gemini chat is not configured.",
            }

        if retrieval["status"] == "insufficient_context":
            print(f"AdaptiveTutorEngine[{request_id}]: returning insufficient-context fallback", flush=True)
            return {
                "text": self.generate_general_fallback(payload.message, payload.language, payload.mode),
                "sources": [],
                "candidate_sources": candidate_sources,
                "grounding_status": "insufficient_context",
                "retrieval_note": retrieval["note"],
                "retrieval_attempts": retrieval["attempts"],
                "effective_hint_level": effective_hint_level,
                "hint_strategy": hint_strategy,
                "should_escalate_next": False,
                "learning_state_note": "Source context was insufficient, so the Socratic source flow was skipped.",
                "check_difficulty": check_difficulty,
                "learning_direction": learning_direction,
                "active_question": clean_active_question,
                "is_follow_up": is_follow_up,
                "quick_check": None,
                "session_outcome": {
                    "completed": False,
                    "confidence_score": 0.0,
                    "mastered_concept": None,
                    "evidence": [],
                    "suggested_next_concept": None,
                    "reason": "Source context was insufficient.",
                },
            }

        is_completed_quick_check = (
            effective_hint_level >= 4
            and "quick check response" in payload.message.lower()
            and "correct: true" in payload.message.lower()
        )
        if is_completed_quick_check:
            session_outcome = self.build_session_outcome(
                payload,
                turn_plan,
                effective_hint_level,
                {"text": "", "quick_check": None},
                sources,
                retrieval_question,
            )
            next_concept = session_outcome.get("suggested_next_concept") or {}
            next_line = (
                f" The next source-grounded concept to study is {next_concept.get('name')}."
                if next_concept.get("name")
                else ""
            )
            print(
                f"AdaptiveTutorEngine[{request_id}]: returning fast completion outcome "
                f"next={next_concept.get('name')!r}",
                flush=True,
            )
            return {
                "text": (
                    "You have shown enough understanding of this concept for now. "
                    f"I have added it to your learning map with {round(session_outcome['confidence_score'] * 100)}% confidence."
                    f"{next_line}"
                ),
                "sources": sources,
                "candidate_sources": candidate_sources,
                "grounding_status": retrieval["status"],
                "retrieval_note": retrieval["note"],
                "retrieval_attempts": retrieval["attempts"],
                "effective_hint_level": effective_hint_level,
                "hint_strategy": hint_strategy,
                "should_escalate_next": False,
                "learning_state_note": state_note,
                "check_difficulty": check_difficulty,
                "learning_direction": learning_direction,
                "active_question": clean_active_question,
                "is_follow_up": is_follow_up,
                "quick_check": None,
                "session_outcome": session_outcome,
            }

        try:
            socratic = self.generate_socratic_response(
                response_payload,
                sources,
                effective_hint_level,
                learning_state,
                check_difficulty,
                learning_direction,
            )
            session_outcome = self.build_session_outcome(
                payload,
                turn_plan,
                effective_hint_level,
                socratic,
                sources,
                retrieval_question,
            )

            print(
                f"AdaptiveTutorEngine[{request_id}]: returning grounded response "
                f"hint={effective_hint_level} quick_check={bool(socratic['quick_check'])} "
                f"completed={session_outcome['completed']}",
                flush=True,
            )
            return {
                "text": socratic["text"],
                "sources": sources,
                "candidate_sources": candidate_sources,
                "grounding_status": retrieval["status"],
                "retrieval_note": retrieval["note"],
                "retrieval_attempts": retrieval["attempts"],
                "effective_hint_level": effective_hint_level,
                "hint_strategy": hint_strategy,
                "should_escalate_next": should_escalate_next,
                "learning_state_note": state_note,
                "check_difficulty": check_difficulty,
                "learning_direction": learning_direction,
                "active_question": clean_active_question,
                "is_follow_up": is_follow_up,
                "quick_check": socratic["quick_check"],
                "session_outcome": session_outcome,
            }
        except Exception as exc:
            print(f"AdaptiveTutorEngine[{request_id}]: chat model error: {exc}", flush=True)
            return {
                "text": self.fallback_reply(payload.message, sources, payload.mode),
                "sources": sources,
                "candidate_sources": candidate_sources,
                "grounding_status": retrieval["status"],
                "retrieval_note": retrieval["note"],
                "retrieval_attempts": retrieval["attempts"],
                "effective_hint_level": effective_hint_level,
                "hint_strategy": hint_strategy,
                "should_escalate_next": should_escalate_next,
                "learning_state_note": state_note,
                "check_difficulty": check_difficulty,
                "learning_direction": learning_direction,
                "active_question": clean_active_question,
                "is_follow_up": is_follow_up,
                "quick_check": None,
                "session_outcome": {
                    "completed": False,
                    "confidence_score": 0.0,
                    "mastered_concept": None,
                    "evidence": [],
                    "suggested_next_concept": None,
                    "reason": "Model fallback was used.",
                },
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
    source = engine.ingest_upload(file)
    return {
        "source": source,
        "concept_graph": engine.current_concept_graph(),
        "message": "Source uploaded, extracted, chunked, and indexed successfully.",
    }


@app.get("/api/sources/current")
async def current_source_endpoint():
    return {
        "source": engine.current_source,
        "concept_graph": engine.current_concept_graph(),
        "rag_source_file": engine.rag_source_file,
        "rag_enabled": engine.retriever is not None,
    }


@app.get("/api/sources/concept-graph")
async def concept_graph_endpoint():
    if not engine.current_source:
        raise HTTPException(status_code=404, detail="No active source.")
    return {
        "source": engine.current_source,
        "concept_graph": engine.current_concept_graph(),
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
        "concept_graph_available": bool(engine.current_concept_graph()),
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

