# Security

These notes apply to Wingman 4.1.0.

Wingman stores private relationship information. Run it on a trusted machine and protect the project directory, database, logs, exports, backups, and `.env` file.

## Local boundary

The web server binds to `127.0.0.1` by default and the dashboard does not require a password. This is intentional for a single-user local application. Do not bind it to a public interface, expose it through a reverse proxy, or forward the port without adding authentication and transport protection.

Telegram access is limited to the configured numeric owner ID. Telegram usernames are not used for authorization.

## Secrets

Telegram tokens and OpenAI API keys are read from environment values. The Settings page can update them for local convenience, but the values are written to the plaintext `.env` file. The dashboard masks them and API request snapshots do not include them.

Do not commit `.env`, API keys, Telegram tokens, database files, logs, JSON exports, or backups. Use file permissions that limit access to the local owner.

## Data handling

Conversation content, memories, notes, planning records, prompts, retrieval logs, and API snapshots may contain sensitive relationship information. JSON exports exclude embeddings and secrets, but they still contain private user data. Store exports and backups securely.

JSON import accepts versioned application exports and forces imported records to the current owner. Do not import untrusted files into a live database without reviewing them first.

## Model and tool safety

The editable prompt controls style only. Application code remains responsible for authorization, memory ownership, safety guidance, tool schemas, validation, transactions, and audit records.

Memory search and planning search are read-only. Memory and planning writes are validated and audited. Uncertain personal observations use a confirmation proposal flow, while explicit save requests can create several valid memories in one turn. Planning tools check ownership, linked records, duplicate names and dates, and required event times.

OpenAI receives the conversation content required for replies and embeddings according to the configured API use. Do not use Wingman for medical, legal, financial, or other high-stakes decisions.

Reasoning content is requested in encrypted form for stateless follow-up requests. It is not exposed as readable chain-of-thought in the dashboard.

## Reporting concerns

If you find a security problem, do not publish private data in an issue. Contact the repository owner through a private channel and include a minimal reproduction.
