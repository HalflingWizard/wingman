# Security

Wingman stores private relationship information. Run it on a trusted Linux machine and keep the data directory private.

The web server binds to `127.0.0.1` by default and accepts Telegram messages only from the configured numeric owner ID. Telegram usernames are not used for authorization.

The production web application requires a local administrator password on first use. Passwords are stored as PBKDF2-HMAC-SHA256 hashes in a file with mode `0600`. Authenticated sessions use HttpOnly, SameSite cookies. POST requests require a session-specific CSRF token.

API keys and Telegram tokens are still read from environment variables. The settings page only reports whether they are configured and never returns their values. Do not commit `.env` files, API keys, bot tokens, authentication files, or database files. Encrypted secret storage and login rate limiting are still future work.

JSON exports exclude embeddings and secrets. Database backups are written under the configured data directory with mode `0600`. Protect this directory and manually copy backups to a separate secure location.

This project is not designed for medical, legal, financial, or highly sensitive secrets. OpenAI API use sends conversation content to OpenAI according to the account and API settings in use.
