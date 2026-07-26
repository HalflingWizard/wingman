# Wingman 4.2.0

Wingman 4.2.0 improves diagnostic retention and makes bundled video messages safer to process.

## Highlights

- Dashboard Logs now keeps the latest 100 tool executions, agent runs, and runtime errors.
- API Calls now keeps the latest 100 model calls.
- Video frame sampling avoids the exact end of a video stream, where some codecs produce empty files.
- Empty image and video-frame attachments are detected before request construction.
- Bundled video messages with captions or nearby text no longer send empty image data URLs to OpenAI.
- The release is versioned as 4.2.0 across the package, dashboard, README, and project documentation.
