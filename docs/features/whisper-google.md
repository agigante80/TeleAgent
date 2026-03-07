# Google Speech-to-Text Voice Transcription

> Status: **Planned** | Priority: Low

Enable voice transcription using the Google Cloud Speech-to-Text API.

## Configuration

```env
WHISPER_PROVIDER=google
GOOGLE_APPLICATION_CREDENTIALS=/data/gcp-key.json   # service account key
```

## Design

- `GoogleTranscriber` class in `src/transcriber.py`
- Uses `google-cloud-speech` Python client library
- Supports a wider range of audio formats natively than Whisper
- Per-minute billing via Google Cloud

## Dependencies to Add

```
google-cloud-speech>=2.21
```

## Notes

- Audio must be converted to a format Google accepts (LINEAR16 or FLAC recommended)
- The existing `transcriber.py` abstraction makes adding this provider straightforward — only the transcription call changes
- Requires a Google Cloud project and billing enabled
