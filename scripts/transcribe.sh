#!/usr/bin/env bash
#
# Transcribe an audio file with speaker diarisation.
#
# Usage:
#   transcribe.sh [--backend parakeet|assemblyai] [--output-dir DIR] <audio-file>
#
# Backends:
#   parakeet    (default) Parakeet MLX + FluidAudio. Local, fast, English only.
#   assemblyai  Cloud. Multi-language. Requires ASSEMBLYAI_API_KEY in the
#               skill's .env.
#
# Environment:
#   TRANSCRIBE_REMOVE_FILLERS=0   Skip filler-word cleanup of the markdown
#                                 transcript (parakeet backend only).
#
# Prints `transcript_path:` and, for the parakeet backend, `srt_path:` on stdout.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

BACKEND="parakeet"
OUTPUT_DIR=""
AUDIO_FILE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --backend)
      BACKEND="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      sed -n '3,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
    *)
      if [ -n "$AUDIO_FILE" ]; then
        # Second positional argument is the output directory.
        OUTPUT_DIR="$1"
      else
        AUDIO_FILE="$1"
      fi
      shift
      ;;
  esac
done

if [ -z "$AUDIO_FILE" ]; then
  echo "Usage: transcribe.sh [--backend parakeet|assemblyai] [--output-dir DIR] <audio-file>" >&2
  exit 2
fi

if [ ! -f "$AUDIO_FILE" ]; then
  echo "Audio file not found: $AUDIO_FILE" >&2
  exit 1
fi

AUDIO_DIR="$(cd "$(dirname "$AUDIO_FILE")" && pwd)"
AUDIO_BASENAME="$(basename "$AUDIO_FILE" | sed 's/\.[^.]*$//')"
OUTPUT_DIR="${OUTPUT_DIR:-$AUDIO_DIR}"
mkdir -p "$OUTPUT_DIR"

TRANSCRIPT_PATH="${OUTPUT_DIR}/${AUDIO_BASENAME}.md"
SRT_PATH="${OUTPUT_DIR}/${AUDIO_BASENAME}.srt"

# ---------------------------------------------------------------------------
# Parakeet MLX + FluidAudio (default)
# ---------------------------------------------------------------------------
run_parakeet() {
  if [ ! -f "$HOME/.local/bin/fluidaudio" ]; then
    echo "FluidAudio not installed. Run the setup script:" >&2
    echo "  bash ${SCRIPT_DIR}/setup_fluidaudio.sh" >&2
    exit 1
  fi

  if [ ! -f "$HOME/.local/bin/parakeet-mlx" ]; then
    echo "parakeet-mlx not installed. Install it with:" >&2
    echo "  uv tool install parakeet-mlx" >&2
    exit 1
  fi

  local duration use_chunked
  duration="$(ffprobe -v error -show_entries format=duration \
    -of default=noprint_wrappers=1:nokey=1 "$AUDIO_FILE" | cut -d. -f1)"
  echo "Audio duration: ${duration} seconds" >&2

  # FluidAudio crashes with std::overflow_error at ~3h 5m, so anything over
  # 3 hours is chunked. See REFERENCE.md.
  if [ "$duration" -gt 10800 ]; then
    echo "Long audio detected — using chunked FluidAudio approach" >&2
    use_chunked=true
  else
    use_chunked=false
  fi

  # --- Transcription -------------------------------------------------------
  if [ "$use_chunked" = true ]; then
    # --local-attention reduces memory use on very long files.
    "$HOME/.local/bin/parakeet-mlx" \
      --local-attention \
      --output-format all \
      --output-dir "$OUTPUT_DIR" \
      "$AUDIO_FILE"
  else
    "$HOME/.local/bin/parakeet-mlx" \
      --output-format all \
      --output-dir "$OUTPUT_DIR" \
      "$AUDIO_FILE"
  fi

  rm -f "${OUTPUT_DIR}/${AUDIO_BASENAME}.json" \
        "${OUTPUT_DIR}/${AUDIO_BASENAME}.vtt" \
        "${OUTPUT_DIR}/${AUDIO_BASENAME}.txt"

  # --- Diarisation ---------------------------------------------------------
  local fluidaudio_json="${OUTPUT_DIR}/${AUDIO_BASENAME}_speakers.json"

  if [ "$use_chunked" = false ]; then
    "$HOME/.local/bin/fluidaudio" process "$AUDIO_FILE" \
      --output "$fluidaudio_json" --threshold 0.5
  else
    local chunk_dir chunk_size overlap chunk_num start
    chunk_dir="$(mktemp -d "${TMPDIR:-/tmp}/fluidaudio_chunks.XXXXXX")"
    chunk_size=7200   # 2-hour chunks
    overlap=30

    chunk_num=0
    start=0
    while [ "$start" -lt "$duration" ]; do
      ffmpeg -y -i "$AUDIO_FILE" -ss "$start" -t $((chunk_size + overlap)) \
        -acodec copy "$chunk_dir/chunk_${chunk_num}.mp3" 2>/dev/null
      chunk_num=$((chunk_num + 1))
      start=$((start + chunk_size))
    done

    local i
    for i in $(seq 0 $((chunk_num - 1))); do
      "$HOME/.local/bin/fluidaudio" process "$chunk_dir/chunk_${i}.mp3" \
        --output "$chunk_dir/speakers_${i}.json" \
        --threshold 0.5 &
    done
    wait

    local chunk_files=()
    for i in $(seq 0 $((chunk_num - 1))); do
      chunk_files+=("$chunk_dir/speakers_${i}.json")
    done

    python3 "${SCRIPT_DIR}/merge_fluidaudio_chunks.py" \
      "$fluidaudio_json" \
      --chunks "${chunk_files[@]}" \
      --chunk-size "$chunk_size" \
      --overlap "$overlap"

    rm -rf "$chunk_dir"
  fi

  # --- Align and clean up --------------------------------------------------
  python3 "${SCRIPT_DIR}/align_speakers.py" \
    "$SRT_PATH" \
    "$fluidaudio_json" \
    "$TRANSCRIPT_PATH"

  rm -f "$fluidaudio_json"

  if [ "${TRANSCRIBE_REMOVE_FILLERS:-1}" != "0" ]; then
    python3 "${SCRIPT_DIR}/cleanup_filler_words.py" \
      "$TRANSCRIPT_PATH" \
      --backup
  fi

  echo "transcript_path: ${TRANSCRIPT_PATH}"
  echo "srt_path: ${SRT_PATH}"
}

# ---------------------------------------------------------------------------
# AssemblyAI (cloud)
# ---------------------------------------------------------------------------
run_assemblyai() {
  if [ ! -f "${SKILL_DIR}/.env" ]; then
    echo "Missing ${SKILL_DIR}/.env with ASSEMBLYAI_API_KEY" >&2
    exit 1
  fi
  # shellcheck source=/dev/null
  source "${SKILL_DIR}/.env"

  local upload_url transcript_id status_response status
  upload_url="$(curl -s --request POST \
    --url 'https://api.assemblyai.com/v2/upload' \
    --header "authorization: ${ASSEMBLYAI_API_KEY}" \
    --header 'content-type: application/octet-stream' \
    --data-binary @"$AUDIO_FILE" | jq -r '.upload_url')"

  if [ -z "$upload_url" ] || [ "$upload_url" = "null" ]; then
    echo "AssemblyAI upload failed" >&2
    exit 1
  fi

  transcript_id="$(curl -s --request POST \
    --url 'https://api.assemblyai.com/v2/transcript' \
    --header "authorization: ${ASSEMBLYAI_API_KEY}" \
    --header 'content-type: application/json' \
    --data "{\"audio_url\": \"${upload_url}\", \"speaker_labels\": true}" \
    | jq -r '.id')"

  local raw_json="${OUTPUT_DIR}/${AUDIO_BASENAME}_assemblyai.json"
  while true; do
    status_response="$(curl -s --request GET \
      --url "https://api.assemblyai.com/v2/transcript/${transcript_id}" \
      --header "authorization: ${ASSEMBLYAI_API_KEY}")"
    status="$(echo "$status_response" | jq -r '.status')"

    if [ "$status" = "completed" ]; then
      echo "$status_response" > "$raw_json"
      break
    elif [ "$status" = "error" ]; then
      echo "AssemblyAI error: $(echo "$status_response" | jq -r '.error')" >&2
      exit 1
    fi
    sleep 3
  done

  jq -r '.utterances[] | "**Speaker \(.speaker):** \(.text)\n"' \
    "$raw_json" > "$TRANSCRIPT_PATH"

  rm -f "$raw_json"

  echo "transcript_path: ${TRANSCRIPT_PATH}"
}

case "$BACKEND" in
  parakeet)   run_parakeet ;;
  assemblyai) run_assemblyai ;;
  *)
    echo "Unknown backend: $BACKEND (expected 'parakeet' or 'assemblyai')" >&2
    exit 2
    ;;
esac
