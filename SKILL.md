---
name: transcribe-audio
description: Transcribe audio files using Parakeet MLX with speaker diarisation. Internal skill used by youtube-transcribe and transcribe-call. Can also be invoked directly with "transcribe [audio file path]" or "transcribe this audio".
---

# Transcribe Audio Skill

Fast local audio transcription with speaker diarisation. Always outputs a diarised transcript with speaker labels.

**Backends:**
- **Parakeet + FluidAudio** (default): Fast, local, runs on Apple Silicon. Transcription + speaker identification.
- **AssemblyAI** (cloud): Use only when user explicitly requests "AssemblyAI", "cloud transcription", or for non-English audio.

## Prerequisites

### For local transcription (default)
- `parakeet-mlx` at `~/.local/bin/parakeet-mlx`
- `fluidaudio` CLI at `~/.local/bin/fluidaudio`
- `ffmpeg` for audio format conversion (if needed)

**If Parakeet is not installed:**
```bash
uv tool install parakeet-mlx
```

**If FluidAudio is not installed:**
```bash
bash ~/.claude/skills/transcribe-audio/scripts/setup_fluidaudio.sh
```

### For AssemblyAI (cloud - only when explicitly requested)
- AssemblyAI API key stored in `~/.claude/skills/transcribe-audio/.env` as `ASSEMBLYAI_API_KEY`
- `curl` for API requests

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
AUDIO_DIR=$(dirname "${AUDIO_FILE}")
AUDIO_BASENAME=$(basename "${AUDIO_FILE}" | sed 's/\.[^.]*$//')
OUTPUT_DIR="${OUTPUT_DIR:-$AUDIO_DIR}"
TRANSCRIPT_PATH="${OUTPUT_DIR}/${AUDIO_BASENAME}.md"
SRT_PATH="${OUTPUT_DIR}/${AUDIO_BASENAME}.srt"
```

### Step 3: Choose transcription method

**Default:** Use Parakeet + FluidAudio (Step 3a)
**If user explicitly requests AssemblyAI/cloud:** Use AssemblyAI (Step 3b)

---

### Step 3a: Local transcription with Parakeet + FluidAudio (default)

#### 3a.1: Check FluidAudio is installed

```bash
if [ ! -f ~/.local/bin/fluidaudio ]; then
    echo "FluidAudio not installed. Run setup script:"
    echo "  bash ~/.claude/skills/transcribe-audio/scripts/setup_fluidaudio.sh"
    exit 1
fi
```

#### 3a.2: Run Parakeet and FluidAudio in parallel

```bash
# Start FluidAudio diarisation in background
FLUIDAUDIO_JSON="${OUTPUT_DIR}/${AUDIO_BASENAME}_speakers.json"
~/.local/bin/fluidaudio process "${AUDIO_FILE}" --output "${FLUIDAUDIO_JSON}" --threshold 0.7 &
FLUIDAUDIO_PID=$!

# Run Parakeet transcription (foreground)
~/.local/bin/parakeet-mlx \
  --output-format all \
  --output-dir "${OUTPUT_DIR}" \
  "${AUDIO_FILE}"

# Delete formats we don't need
rm -f "${OUTPUT_DIR}/${AUDIO_BASENAME}.json" "${OUTPUT_DIR}/${AUDIO_BASENAME}.vtt" "${OUTPUT_DIR}/${AUDIO_BASENAME}.txt"
```

#### 3a.3: Wait for FluidAudio and align speakers

```bash
# Wait for FluidAudio to complete
wait $FLUIDAUDIO_PID

# Run alignment script to merge transcript with speaker segments
python3 ~/.claude/skills/transcribe-audio/scripts/align_speakers.py \
  "${SRT_PATH}" \
  "${FLUIDAUDIO_JSON}" \
  "${TRANSCRIPT_PATH}"

# Clean up intermediate files
rm -f "${FLUIDAUDIO_JSON}"
```

#### 3a.4: Return results

```bash
echo "transcript_path: ${TRANSCRIPT_PATH}"
echo "srt_path: ${SRT_PATH}"
cat "${TRANSCRIPT_PATH}"
```

---

### Step 3b: AssemblyAI transcription (only when explicitly requested)

Use this only when the user explicitly asks for "AssemblyAI", "cloud transcription", or needs non-English audio support.

#### 3b.1: Load API key and upload the audio file

```bash
source ~/.claude/skills/transcribe-audio/.env

UPLOAD_RESPONSE=$(curl -s --request POST \
  --url 'https://api.assemblyai.com/v2/upload' \
  --header "authorization: ${ASSEMBLYAI_API_KEY}" \
  --header 'content-type: application/octet-stream' \
  --data-binary @"${AUDIO_FILE}")

UPLOAD_URL=$(echo "$UPLOAD_RESPONSE" | jq -r '.upload_url')
```

#### 3b.2: Request transcription with speaker diarisation

```bash
TRANSCRIPT_RESPONSE=$(curl -s --request POST \
  --url 'https://api.assemblyai.com/v2/transcript' \
  --header "authorization: ${ASSEMBLYAI_API_KEY}" \
  --header 'content-type: application/json' \
  --data "{
    \"audio_url\": \"${UPLOAD_URL}\",
    \"speaker_labels\": true
  }")

TRANSCRIPT_ID=$(echo "$TRANSCRIPT_RESPONSE" | jq -r '.id')
```

#### 3b.3: Poll for completion

```bash
while true; do
  STATUS_RESPONSE=$(curl -s --request GET \
    --url "https://api.assemblyai.com/v2/transcript/${TRANSCRIPT_ID}" \
    --header "authorization: ${ASSEMBLYAI_API_KEY}")

  STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.status')

  if [ "$STATUS" = "completed" ]; then
    echo "$STATUS_RESPONSE" > "${OUTPUT_DIR}/${AUDIO_BASENAME}_assemblyai.json"
    break
  elif [ "$STATUS" = "error" ]; then
    echo "Error: $(echo "$STATUS_RESPONSE" | jq -r '.error')"
    exit 1
  fi

  sleep 3
done
```

#### 3b.4: Format diarised transcript

```bash
# Extract and format diarised transcript as markdown with bold speaker labels
jq -r '.utterances[] | "**Speaker \(.speaker):** \(.text)\n"' \
  "${OUTPUT_DIR}/${AUDIO_BASENAME}_assemblyai.json" \
  > "${TRANSCRIPT_PATH}"

# Clean up
rm -f "${OUTPUT_DIR}/${AUDIO_BASENAME}_assemblyai.json"
```

---

## Output

Return to the calling skill/user:
- **transcript_path**: Absolute path to the generated transcript file (.md with speaker labels)
- **srt_path**: Absolute path to the generated .srt file (with timestamps)
- **transcript_text**: The full transcript content

All transcripts are markdown with bold speaker labels:
```markdown
**Speaker 1:** Hello, how are you?

**Speaker 2:** I'm doing well, thanks for asking.

**Speaker 1:** Great to hear!
```

## Notes

### Local transcription (default)
- English only (Parakeet is optimised for English)
- Very fast: ~5 minutes for 1 hour of audio on M4 Pro
- Runs entirely locally - no internet required
- Speaker identification via FluidAudio (runs on Apple Neural Engine)

### AssemblyAI (cloud - only when requested)
- Supports multiple languages (auto-detected)
- Requires internet connection and API key
- Slower due to upload and cloud processing
- Cost: ~$0.01/minute
- Use for: non-English audio, or when explicitly requested
