# Wingman 4.4.0

Wingman 4.4.0 makes retrieval intentional and strengthens Telegram media intake.

## Highlights

- The application no longer injects all saved memories and planning records into every request.
- The model now receives detailed guidance for using memory and planning search tools only when relevant.
- Unrelated high-importance memories no longer bypass relevance matching.
- Telegram files are classified by MIME type and filename before processing.
- Video documents, audio files, animations, normal videos, and video notes use the correct processing path.
- Incoming messages are written to the dashboard before media processing begins.
- Media failures are recorded with detailed diagnostics and reported clearly to the owner.
- Added schemas and prompt guidance for focused retrieval, duplicate checks, memory status, confidence, and importance.
