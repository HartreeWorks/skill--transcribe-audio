---
name: transcribe-audio
description: Transcribe local audio with diarisation.
---

# Transcribe Audio Skill

Transcribe an audio file with speaker diarisation, then identify the speakers by name where the evidence supports it.

## Transcribe

```bash
bash ~/.claude/skills/transcribe-audio/scripts/transcribe.sh \
  [--output-dir /path/to/output] \
  "/absolute/path/to/audio.mp3"
```

The script handles duration checks, chunking for long files, diarisation, alignment and filler-word cleanup. It prints `transcript_path:` and `srt_path:`, and defaults the output directory to the audio file's own directory.

**Backends:**

- **Parakeet + FluidAudio** (default) — local, fast, English only. Requires `parakeet-mlx` and `fluidaudio` in `~/.local/bin`; if either is missing the script says how to install it.
- **AssemblyAI** — add `--backend assemblyai`. Use only when the user explicitly asks for AssemblyAI or cloud transcription, or when the audio is not in English. Costs about $0.01/minute and needs `ASSEMBLYAI_API_KEY` in the skill's `.env`.

Set `TRANSCRIBE_REMOVE_FILLERS=0` to keep "um" and "uh" in the markdown transcript.

## Identify speaker names

The pipeline outputs generic `Speaker 1` / `Speaker 2` labels. Before presenting the transcript, try to replace them with real names. Gather hints from several sources and cross-reference them:

1. **Transcript content** — the most reliable source. Scan the opening paragraphs for self-introductions ("This is…", "I'm…", "My name is…"), host introductions ("Our guest is…", "…is NAME. NAME is a…"), and direct address ("NAME, welcome to the show").
2. **Audio filename** — kebab- or snake-case names often carry both guest and show: `david-sloan-wilson-trajectory-podcast.mp3`.
3. **Conversation context** — the user may already have named the participants ("transcribe this interview with…").
4. **YouTube metadata**, when invoked via `youtube-transcribe` — `~/.claude/skills/youtube-transcribe/data/metadata/<audio-basename>.json`, whose `title`, `channel` and `description` usually name the guest and host.

Apply a name only where the sources agree and you are confident. Keep the generic label when uncertain — a wrong name is worse than `Speaker 2`.

## Output

Return to the calling skill or user:

- **transcript_path** — markdown with bold speaker labels
- **srt_path** — timestamped subtitles (Parakeet backend only)
- **transcript_text** — the transcript content

```markdown
**David Sloan Wilson:** Hello, how are you?

**Daniel Faggella:** I'm doing well, thanks for asking.
```

## Reference

`REFERENCE.md` documents the pipeline's mechanics: the long-audio chunking thresholds, the speaker-separation threshold, and the exact filler-word cleanup rules.
