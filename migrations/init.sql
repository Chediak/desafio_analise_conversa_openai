CREATE TABLE IF NOT EXISTS analysis (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL,
    satisfaction INTEGER CHECK (satisfaction >= 0 AND satisfaction <= 10),
    summary TEXT NOT NULL,
    improvement TEXT NOT NULL,
    key_points TEXT NOT NULL,
    resolution BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analysis_conversation_id ON analysis(conversation_id); 