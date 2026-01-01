---
name: transcribe-audio
description: Transcribe audio files using Parakeet MLX. Internal skill used by youtube-transcribe and transcribe-call. Can also be invoked directly with "transcribe [audio file path]" or "transcribe this audio".
---

# Transcribe Audio Skill

Core audio transcription with two backends:
- **Parakeet MLX** (default): Fast, local, runs on Apple Silicon. No speaker identification.
- **AssemblyAI** (optional): Cloud-based, supports speaker diarisation. Use when the user explicitly requests diarisation, speaker identification, or "who said what".

## Prerequisites

### For Parakeet (default)
- `parakeet-mlx` at `~/.local/bin/parakeet-mlx`
- `ffmpeg` for audio format conversion (if needed)

### For AssemblyAI (diarisation)
- AssemblyAI API key stored in `~/.claude/skills/transcribe-audio/.env` as `ASSEMBLYAI_API_KEY`
- `curl` for API requests

## Input

When invoked, you should receive or determine:
- **Audio file path**: Absolute path to audio file (MP3, M4A, WAV, FLAC, etc.)
- **Output directory** (optional): Where to save transcript. Defaults to same directory as audio file.
- **Diarisation** (optional): Whether to identify speakers. Defaults to `false`.

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
TRANSCRIPT_PATH="${OUTPUT_DIR}/${AUDIO_BASENAME}.txt"  # .md for diarised transcripts
SRT_PATH="${OUTPUT_DIR}/${AUDIO_BASENAME}.srt"
```

### Step 3: Choose transcription method

**If diarisation is NOT requested (default):** Use Parakeet MLX (Step 3a)
**If diarisation IS requested:** Use AssemblyAI (Step 3b)

---

### Step 3a: Parakeet MLX transcription (default - no diarisation)

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

---

### Step 3b: AssemblyAI transcription (with diarisation)

#### 3b.1: Load API key and upload the audio file

```bash
# Load API key from .env
source ~/.claude/skills/transcribe-audio/.env

# Upload audio file to AssemblyAI
UPLOAD_RESPONSE=$(curl -s --request POST \
  --url 'https://api.assemblyai.com/v2/upload' \
  --header "authorization: ${ASSEMBLYAI_API_KEY}" \
  --header 'content-type: application/octet-stream' \
  --data-binary @"${AUDIO_FILE}")

UPLOAD_URL=$(echo "$UPLOAD_RESPONSE" | jq -r '.upload_url')
echo "Upload URL: $UPLOAD_URL"
```

#### 3b.2: Request transcription with speaker diarisation

```bash
# Request transcription with speaker diarisation enabled
TRANSCRIPT_RESPONSE=$(curl -s --request POST \
  --url 'https://api.assemblyai.com/v2/transcript' \
  --header "authorization: ${ASSEMBLYAI_API_KEY}" \
  --header 'content-type: application/json' \
  --data "{
    \"audio_url\": \"${UPLOAD_URL}\",
    \"speaker_labels\": true
  }")

TRANSCRIPT_ID=$(echo "$TRANSCRIPT_RESPONSE" | jq -r '.id')
echo "Transcript ID: $TRANSCRIPT_ID"
```

#### 3b.3: Poll for completion

```bash
# Poll until transcription is complete
while true; do
  STATUS_RESPONSE=$(curl -s --request GET \
    --url "https://api.assemblyai.com/v2/transcript/${TRANSCRIPT_ID}" \
    --header "authorization: ${ASSEMBLYAI_API_KEY}")

  STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.status')
  echo "Status: $STATUS"

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

After receiving the completed response, format it as a readable markdown transcript with bold speaker labels:

```bash
# Extract and format diarised transcript as markdown with bold speaker labels
jq -r '.utterances[] | "**Speaker \(.speaker):** \(.text)\n"' \
  "${OUTPUT_DIR}/${AUDIO_BASENAME}_assemblyai.json" \
  > "${OUTPUT_DIR}/${AUDIO_BASENAME}.md"

# Also save plain text version (without speaker labels) for compatibility
jq -r '.text' "${OUTPUT_DIR}/${AUDIO_BASENAME}_assemblyai.json" \
  > "${OUTPUT_DIR}/${AUDIO_BASENAME}_plain.txt"
```

#### 3b.5: Generate SRT with speaker labels

```bash
# Generate SRT file with speaker labels and timestamps
jq -r '
  .utterances | to_entries | .[] |
  "\(.key + 1)\n\(
    ((.value.start / 1000) | floor | "\(. / 3600 | floor | tostring | if length < 2 then "0" + . else . end):\((. % 3600) / 60 | floor | tostring | if length < 2 then "0" + . else . end):\(. % 60 | tostring | if length < 2 then "0" + . else . end)")
  ),000 --> \(
    ((.value.end / 1000) | floor | "\(. / 3600 | floor | tostring | if length < 2 then "0" + . else . end):\((. % 3600) / 60 | floor | tostring | if length < 2 then "0" + . else . end):\(. % 60 | tostring | if length < 2 then "0" + . else . end)")
  ),000\nSpeaker \(.value.speaker): \(.value.text)\n"
' "${OUTPUT_DIR}/${AUDIO_BASENAME}_assemblyai.json" > "${SRT_PATH}"
```

Note: The SRT generation jq command is complex. If it fails, use a simpler Python script or just provide the diarised .txt file.

---

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
- **transcript_path**: Absolute path to the generated transcript file (.txt for Parakeet, .md for diarised)
- **srt_path**: Absolute path to the generated .srt file (with timestamps)
- **transcript_text**: The full transcript content

For diarised transcripts, the .md file will contain bold speaker labels:
```markdown
**Speaker A:** Hello, how are you?

**Speaker B:** I'm doing well, thanks for asking.

**Speaker A:** Great to hear!
```

## Notes

### Parakeet (default)
- English only (Parakeet is optimised for English)
- For other languages, consider using whisper-cpp instead
- Supported input formats: MP3, M4A, WAV, FLAC, OGG, and most audio formats ffmpeg can decode
- If the input format is not directly supported by Parakeet, ffmpeg will be used automatically for conversion

### AssemblyAI (diarisation)
- Requires internet connection and API key
- Supports multiple languages (auto-detected)
- Speaker diarisation identifies different speakers but doesn't name them (Speaker A, B, C, etc.)
- Slower than Parakeet due to upload and cloud processing
- Cost: Check AssemblyAI pricing (typically ~$0.01/minute for speech-to-text + diarisation)
