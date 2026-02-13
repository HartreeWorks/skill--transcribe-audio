# Transcribe Audio – Reference

## Filler-word cleanup (markdown transcript)

By default, `transcribe-audio` applies a conservative, deterministic post-processing step to remove common filler words from the **markdown transcript only** (it does not modify the `.srt`).

### Toggle

- **Default:** enabled
- **Disable per-run:** set `TRANSCRIBE_REMOVE_FILLERS=0`

### What gets processed

Only diarised markdown transcript lines that match the speaker-label format are modified:

- `**Speaker Name:** <utterance>`

The script preserves the speaker label and rewrites the `<utterance>` portion.

### Removed filler strings

Case-insensitive removal of standalone tokens:

- `um` (including stretched variants: `umm`, `ummm`, …)
- `uh` (including stretched variants: `uhh`, `uhhh`, …)
- `erm` (including stretched variants: `ermm`, `ermmm`, …)
- `er` (exact `er`)

Implementation regex (conceptual):

- `um+ | uh+ | erm+ | er`

### Removal logic (applied in order)

Given an utterance string `text`:

1) **Remove parenthesised filler**
   - Example: `(um)` → removed
   - Pattern: `\(\s*(FILLER)\s*\)`

2) **Remove `FILLER,`** (filler immediately followed by a comma)
   - Example: `Um, I think…` → `I think…`
   - Pattern: `\b(FILLER)\b\s*,\s*`

3) **Remove filler surrounded by spaces**
   - Example: `I uh think` → `I think`
   - Pattern: `\s+\b(FILLER)\b\s+` → single space

4) **Remove filler at start of utterance**
   - Example: `uh okay…` → `okay…`
   - Pattern: `^\s*\b(FILLER)\b\s+`

5) **Remove filler at end of utterance**
   - Example: `I guess, um` → `I guess,`
   - Pattern: `\s+\b(FILLER)\b\s*$`

6) **Remove any remaining standalone filler tokens** (catch-all)
   - Pattern: `\b(FILLER)\b`

### Spacing / punctuation normalisation

After filler removal:

- Collapse multiple spaces/tabs to one space
- Remove spaces before punctuation `, . ; : ! ?`
- Insert a space after punctuation when missing
- Normalise dash characters:
  - `—` and `–` become ` — ` (spaced em dash)
  - ` - ` (spaced hyphen used as a dash) becomes ` — `
  - Hyphens **inside words** (e.g. `self-determination`) are not changed

### Recapitalisation

To keep sentence starts grammatical after removing leading fillers:

- Capitalise the first letter of the utterance if it begins with `[a-z]` (after optional opening quotes/brackets)
- Capitalise the first letter after sentence-ending punctuation: `.`, `!`, `?` (allowing intervening quotes/brackets/spaces)
- Convert standalone `i` to `I`

### Output safety

When run from the skill pipeline, the cleanup can write a side-by-side backup:

- `*.raw.md` – original transcript before cleanup

(Controlled by the `--backup` flag in the cleanup script.)
