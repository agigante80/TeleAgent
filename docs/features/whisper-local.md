# Local Whisper Voice Transcription

> Status: **Planned** | Priority: Low

Enable fully offline voice transcription using the `openai-whisper` Python package.

## Configuration

```env
WHISPER_PROVIDER=local
WHISPER_MODEL=base          # tiny | base | small | medium | large
WHISPER_MODEL_DIR=/data/whisper-models   # cache directory
```

## Design

- `LocalWhisperTranscriber` class in `src/transcriber.py`
- Model files downloaded on first use via `whisper.load_model()`, cached at `WHISPER_MODEL_DIR`
- Model is NOT bundled in the Docker image (keeps image size lean)
- First call is slow (model download); subsequent calls fast (model cached)

## Trade-offs

| Aspect | Local | OpenAI API |
|--------|-------|-----------|
| Cost | Free | Per-minute billing |
| Privacy | On-device | Data sent to OpenAI |
| Speed | Slower (small GPU or CPU) | Fast |
| Offline | ✅ | ❌ |

## Dependencies to Add

```
openai-whisper>=20231117
```

Note: `openai-whisper` requires `ffmpeg` — add `RUN apt-get install -y ffmpeg` to Dockerfile.
