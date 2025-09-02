from ingest import ingest_bytes
from rag import run_for_control
from db import get_session
from oscals_loader import load_controls_and_baselines
from llm_openai import chat_json

app = FastAPI()

@app.on_event("startup")
def load_oscal():
    with get_session() as s:
        load_controls_and_baselines(s)  # idempotent

@app.post("/upload")
async def upload(file: UploadFile):
    blob = await file.read()
    out = ingest_bytes(file.filename, blob, creator="api")
    return out

@app.post("/run")
def run(profile_id: str):
    # Fetch profile, controls in scope
    with get_session() as s:
        controls = s.execute("""SELECT c.id, c.text FROM controls c
                                JOIN tailoring_profiles t ON t.baseline_id = ANY(ARRAY[c.id]) OR true
                             """).fetchall()  # simplify: replace with proper include/exclude
        results = []
        for cid, ctext in controls[:30]:  # limit for MVP
            result = run_for_control(s, emb_model, call_llm, type("C",(),{"id":cid,"text":ctext}))
            results.append(result)
        return {"results": results}
