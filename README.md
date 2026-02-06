# Transcribe Audio

A Claude Code skill for transcribing audio files with speaker diarisation and automatic speaker name identification.

- **Parakeet + FluidAudio** (default): Fast, local transcription with speaker identification. Runs entirely on Apple Silicon (~5 min for 1 hour of audio).
- **AssemblyAI** (optional): Cloud-based, for non-English audio or when explicitly requested.
- **Speaker names**: Automatically identifies speaker names from filename, YouTube metadata, and transcript content.

## Documentation

See [SKILL.md](./SKILL.md) for complete documentation and usage instructions.

## Installation

```bash
npx skills add HartreeWorks/skill--transcribe-audio
```

Or install all HartreeWorks skills: `npx skills add HartreeWorks/skills`

## About

Created by [Peter Hartree](https://x.com/peterhartree). For updates, follow [AI Wow](https://wow.pjh.is), my AI uplift newsletter.

Find more skills at [skills.sh](https://skills.sh) and [HartreeWorks/skills](https://github.com/HartreeWorks/skills).
