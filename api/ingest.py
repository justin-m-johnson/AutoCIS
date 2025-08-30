import hashlib, io
from typing import List, Tuple
from unstructured.partition.auto import partition
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from .models import Document, Chunk
from .db import get_session
from .title_extract import pick_title  # simple heuristics
from .llm_openai import embed_texts

EMBED_MODEL = SentenceTransformer("sentence-transformers/bge-small-en-v1.5")
vecs = embed_texts(texts)

def file_sha256(b: bytes) -> str:
    h = hashlib.sha256(); h.update(b); return h.hexdigest()

def heading_aware_chunks(elements, target_tokens=900, overlap=120) -> List[Tuple[str, dict]]:
    """Return (text, meta) with section_path/page info using unstructured elements."""
    chunks = []
    buf, meta = [], {}
    tokens = 0
    for el in elements:
        text = (el.metadata.text_as_html or el.text or "").strip()
        if not text: continue
        if getattr(el, "category", "") in ("Title", "Header"):
            # flush
            if buf:
                chunks.append((" ".join(buf), meta))
                buf, tokens = [], 0
            meta = {
                "section_path": el.text.strip(),
                "page": (el.metadata.page_number or 1)
            }
        buf.append(el.text.strip())
        tokens += len(el.text.split())
        if tokens >= target_tokens:
            chunks.append((" ".join(buf), meta))
            buf, tokens = buf[-overlap//5:], 0
    if buf:
        chunks.append((" ".join(buf), meta))
    return chunks

def embed(texts: List[str]):
    return EMBED_MODEL.encode(texts, normalize_embeddings=True)

def ingest_bytes(filename: str, blob: bytes, creator: str = "system"):
    elements = partition(file=io.BytesIO(blob), file_filename=filename)
    title = pick_title(elements, fallback=filename)
    sha = file_sha256(blob)

    with get_session() as s:  # type: Session
        doc = Document(canonical_title=title, filename=filename, sha256=sha, filetype=filename.split(".")[-1], created_by=creator)
        s.add(doc); s.flush()

        chs = heading_aware_chunks(elements)
        texts = [t for t,_ in chs]
        vecs = embed(texts)

        for (text, meta), v in zip(chs, vecs):
            c = Chunk(document_id=doc.id,
                      section_path=meta.get("section_path"),
                      page=meta.get("page", 1),
                      char_start=0, char_end=len(text),
                      text=text)
            s.add(c)
            s.flush()
            s.execute("UPDATE chunks SET embedding = %s WHERE id = %s", (list(v), c.id))

        s.commit()
    return {"document_id": doc.id, "title": title}


for (text, meta), v in zip(chs, vecs):
    # insert chunk row first, then update embedding
    c = Chunk(…); s.add(c); s.flush()
    s.execute(
      "UPDATE chunks SET embedding = %s WHERE id = %s",
      (v, c.id)  # PGVector accepts Python list[float]
    )