---
name: transcribe-audio
description: Transcribe audio files using Parakeet MLX. Internal skill used by youtube-transcribe and transcribe-call. Can also be invoked directly with "transcribe [audio file path]" or "transcribe this audio".
---

# Transcribe Audio Skill

Core audio transcription using Parakeet MLX (fast, runs on Apple Silicon).

## Prerequisites

- `parakeet-mlx` at `~/.local/bin/parakeet-mlx`
- `ffmpeg` for audio format conversion (if needed)

## Input

When invoked, you should receive or determine:
- **Audio file path**: Absolute path to audio file (MP3, M4A, WAV, FLAC, etc.)
- **Output directory** (optional): Where to save transcript. Defaults to same directory as audio file.

## Workflow

### Step 1: Validate input file

```bash
# Check file exists
ls -la "${AUDIO_FILE}"

# Get file info
ffprobe -hide_banner "${AUDIO_FILE}" 2>&1 | head -10
```

### Step 2: Determine output location

```bash
# If output directory specified, use it
# Otherwise, use same directory as input file
AUDIO_DIR=$(dirname "${AUDIO_FILE}")
AUDIO_BASENAME=$(basename "${AUDIO_FILE}" | sed 's/\.[^.]*$//')
OUTPUT_DIR="${OUTPUT_DIR:-$AUDIO_DIR}"
TRANSCRIPT_PATH="${OUTPUT_DIR}/${AUDIO_BASENAME}.txt"
SRT_PATH="${OUTPUT_DIR}/${AUDIO_BASENAME}.srt"
```

### Step 3: Run Parakeet MLX transcription

```bash
# Generate all formats (Parakeet only uses the last --output-format if multiple specified)
~/.local/bin/parakeet-mlx \
  --output-format all \
  --output-dir "${OUTPUT_DIR}" \
  "${AUDIO_FILE}"

# Delete formats we don't need (json is 1.2MB, vtt is similar to srt)
rm -f "${OUTPUT_DIR}/${AUDIO_BASENAME}.json" "${OUTPUT_DIR}/${AUDIO_BASENAME}.vtt"
```

Parakeet outputs two files we keep:
- `${AUDIO_BASENAME}.txt` - Plain text transcript for easy reading
- `${AUDIO_BASENAME}.srt` - Timestamped subtitle file for chapter/quote linking

First run downloads the Parakeet model (~1.2GB). Transcription is very fast (~300x realtime on Apple Silicon).

### Step 4: Return results

1. Read the transcript file
2. Report the transcript path
3. Return the full transcript text to the caller

```bash
# Read transcript
cat "${TRANSCRIPT_PATH}"
```

## Output

Return to the calling skill/user:
- **transcript_path**: Absolute path to the generated .txt file
- **srt_path**: Absolute path to the generated .srt file (with timestamps)
- **transcript_text**: The full transcript content

## Notes

- English only (Parakeet is optimized for English)
- For other languages, consider using whisper-cpp instead
- Supported input formats: MP3, M4A, WAV, FLAC, OGG, and most audio formats ffmpeg can decode
- If the input format is not directly supported by Parakeet, ffmpeg will be used automatically for conversion
