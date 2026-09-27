# The demo video

`build.py` turns screenshots of the running app into the 90-second
submission video. Every frame is a real capture. The "sped up" tag marks the
scenes where waiting time was cut. The narration comes from Piper, a local
text-to-speech model, so nothing is sent to a third party.

Needs `ffmpeg`, a Python env with `piper-tts` and `pillow`, and the
`en_US-lessac-medium` Piper voice. The scene screenshots are taken with gstack
`/browse` against `localhost:3100`, `localhost:8026` and the MCP client.
