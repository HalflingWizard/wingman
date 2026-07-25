# Wingman 2.0.0

Wingman 2.0.0 is a local Telegram relationship assistant with memory, retrieval, planning, and a transparent administration dashboard.

## Highlights

- Natural Telegram conversations for one authorized owner
- Durable memories with notes, evidence, confidence, status, and source links
- Hybrid memory retrieval using lexical matching and embeddings
- Memory proposals for uncertain personal observations
- Conversation history, rolling summaries, and dynamic context assembly
- Places, saved ideas, events, and one-time reminders
- `gpt-5-nano` Responses API integration with controlled memory tools
- Complete API request, response, tool, and retrieval inspection
- Editable static conversation guidance through the Context page
- Responsive dashboard with Font Awesome icons and shared navigation
- Local settings editing with masked credential fields
- JSON export and import for user data portability
- SQLite backups and safe Git updates
- Bot pause or resume toggle and automatic port fallback

## Privacy notes

Wingman is local-only by default and intentionally does not include dashboard password authentication. Keep the dashboard bound to `127.0.0.1`. API keys and Telegram tokens can be stored in the local plaintext `.env` file, so protect the project directory and never commit secrets.

## Install

```bash
git clone https://github.com/HalflingWizard/wingman.git
cd wingman
./scripts/install.sh
source .venv/bin/activate
cp .env.example .env
wingman doctor
wingman start
```

## Validation

The release was validated with Ruff, Mypy, and the complete pytest suite.
