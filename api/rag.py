from sqlalchemy import text as sql
from .llm_openai import embed_texts, chat_json

def ann_search(session, qvec, topk=20):
    rows = session.execute(sql("""
      SELECT id, document_id, text, section_path, page,
             1 - (embedding <=> :q) AS score
      FROM chunks
      ORDER BY embedding <=> :q
      LIMIT :k
    """), {"q": qvec, "k": topk}).mappings().all()
    return rows

PROMPT = """You are generating NIST SP 800-53 implementation details.

Control: {control_id}
Official text: {control_text}

Context (organization docs):
{contexts}

Task:
1) Write a concise implementation statement grounded ONLY in the context.
2) List which parameters (assignments/selections) are explicitly covered vs missing.
3) If evidence is insufficient, mark status MISSING and propose 1–3 questions.

Output JSON with fields:
control_id, status, implementation_text, parameters_filled, missing_params, citations
"""

def run_for_control(session, control):
    q = f"{control.id} {control.text}"
    qvec = embed_texts([q])[0]
    ann = ann_search(session, qvec, topk=24)

    doc_titles = {d.id: d.canonical_title
                  for d in session.execute(sql("SELECT id, canonical_title FROM documents")).mappings()}
    for r in ann:
        r["canonical_title"] = doc_titles.get(r["document_id"], "")

    # (optional) BM25 re-rank kept from earlier …
    top = ann[:8]

    contexts = []
    for r in top:
        contexts.append(f"[{r['canonical_title']} | p.{r['page']} | {r.get('section_path','')}] {r['text'][:1200]}")
    ctx = "\n---\n".join(contexts)

    out = chat_json(PROMPT.format(
        control_id=control.id, control_text=control.text, contexts=ctx
    ), system="Return valid JSON. If context is weak, set status=MISSING.")
    return out
