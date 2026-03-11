"""Application constants and configuration."""

CHUNK_WINDOW_SECONDS = 120
CHUNK_CARRY_SNIPPETS = 3
EMBED_MODEL = "llama-text-embed-v2"
EMBED_BATCH_SIZE = 50
SENTINEL_VECTOR = [1e-7] + [0.0] * 1023
CLAUDE_MODEL = "claude-sonnet-4-6"
MAX_VIDEOS_FREE = 3
MAX_QUESTIONS_FREE = 5
MAX_DURATION_FREE = 3600
SESSION_TTL_HOURS = 2
APP_NAME = "AskTheVideo"
APP_URL = "https://app.askthevideo.com"
