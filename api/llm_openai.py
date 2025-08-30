import os, json
from typing import List
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
CHAT_MODEL = os.getenv("LLM_MODEL", "gpt-4.1-mini")

def embed_texts(texts: List[str]) -> List[List[float]]:
    # OpenAI batches up to ~2048 inputs; we’ll keep it simple for MVP
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [d.embedding for d in resp.data]

def chat_json(prompt: str, system: str = None) -> dict:
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=msgs,
        response_format={"type":"json_object"},
        temperature=0.2,
    )
    text = resp.choices[0].message.content
    return json.loads(text)
