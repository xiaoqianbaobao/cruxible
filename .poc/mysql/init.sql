CREATE TABLE IF NOT EXISTS threads (
  thread_id VARCHAR(128) PRIMARY KEY,
  title TEXT NOT NULL,
  metadata JSON NULL,
  created_at DATETIME NULL,
  updated_at DATETIME NULL
);

CREATE TABLE IF NOT EXISTS messages (
  message_id VARCHAR(255) PRIMARY KEY,
  thread_id VARCHAR(128) NOT NULL,
  role VARCHAR(32) NOT NULL,
  content LONGTEXT NOT NULL,
  position INT NOT NULL,
  raw JSON NULL,
  CONSTRAINT fk_messages_thread FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_position ON messages(thread_id, position);
