CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- for gen_random_uuid()

-- Core metadata
CREATE TABLE IF NOT EXISTS documents (
  id SERIAL PRIMARY KEY,
  canonical_title TEXT NOT NULL,
  filename TEXT NOT NULL,
  sha256 TEXT NOT NULL UNIQUE,
  filetype TEXT NOT NULL,
  created_by TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Chunk store (+ embeddings with OpenAI text-embedding-3-large = 3072 dims)
CREATE TABLE IF NOT EXISTS chunks (
  id BIGSERIAL PRIMARY KEY,
  document_id INT REFERENCES documents(id) ON DELETE CASCADE,
  section_path TEXT,
  page INT,
  char_start INT,
  char_end INT,
  text TEXT NOT NULL,
  embedding vector(3072)
);
CREATE INDEX IF NOT EXISTS chunks_docid_idx ON chunks(document_id);
CREATE INDEX IF NOT EXISTS chunks_embedding_ivf_idx
  ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- NIST controls & baselines
CREATE TABLE IF NOT EXISTS controls (
  id TEXT PRIMARY KEY,         -- e.g., 'AC-2'
  family TEXT NOT NULL,        -- 'AC'
  text TEXT NOT NULL,          -- official description
  parameters JSONB DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS baselines (
  id TEXT PRIMARY KEY,         -- 'LOW' | 'MODERATE' | 'HIGH'
  control_ids TEXT[] NOT NULL
);

-- Tailoring + runs + findings
CREATE TABLE IF NOT EXISTS tailoring_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT,
  baseline_id TEXT REFERENCES baselines(id),
  include TEXT[] DEFAULT '{}',
  exclude TEXT[] DEFAULT '{}',
  parameter_overrides JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID REFERENCES tailoring_profiles(id),
  model TEXT,
  top_k INT DEFAULT 8,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS findings (
  run_id UUID REFERENCES runs(id),
  control_id TEXT REFERENCES controls(id),
  status TEXT, -- 'COMPLETE'|'PARTIAL'|'MISSING'
  implementation_text TEXT,
  parameters_filled JSONB,
  missing_params JSONB,
  citations JSONB, -- [{doc_id,title,page,section_path,char_start,char_end}]
  PRIMARY KEY (run_id, control_id)
);

-- Reasonable ANN search defaults
SET ivfflat.probes = 10;
