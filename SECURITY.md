# Security

Wingman stores private relationship information. Run it on a trusted Linux machine and keep the data directory private.

Phase 1 binds the web server to `127.0.0.1` by default and accepts Telegram messages only from the configured numeric owner ID. Telegram usernames are not used for authorization.

Phase 1 reads credentials from environment variables. Do not commit `.env` files, API keys, bot tokens, or database files. Later phases will add encrypted secret storage, authenticated web sessions, CSRF protection, and login rate limiting.

This project is not designed for medical, legal, financial, or highly sensitive secrets. OpenAI API use sends conversation content to OpenAI according to the account and API settings in use.
