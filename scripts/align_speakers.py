#!/usr/bin/env python3
"""
Align speaker diarisation segments with transcription.

Takes:
- Parakeet SRT file (with word/phrase timestamps)
- FluidAudio JSON output (with speaker segments)

Produces:
- Diarised transcript in markdown format with speaker labels
"""

import json
import re
import sys
from pathlib import Path


def parse_srt(srt_path: str) -> list[dict]:
    """Parse SRT file into list of segments with timestamps."""
    segments = []
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by double newline (SRT entry separator)
    entries = re.split(r'\n\n+', content.strip())

    for entry in entries:
        lines = entry.strip().split('\n')
        if len(lines) < 3:
            continue

        # Parse timestamp line: 00:00:00,000 --> 00:00:05,000
        timestamp_match = re.match(
            r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})',
            lines[1]
        )
        if not timestamp_match:
            continue

        # Convert to seconds
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, timestamp_match.groups())
        start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
        end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000

        # Join text lines (subtitle may span multiple lines)
        text = ' '.join(lines[2:])

        segments.append({
            'start': start,
            'end': end,
            'text': text
        })

    return segments


def parse_fluidaudio_json(json_path: str) -> list[dict]:
    """Parse FluidAudio diarisation output."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # FluidAudio output format: list of segments with speakerId, startTimeSeconds, endTimeSeconds
    # Adjust based on actual FluidAudio output format
    segments = []

    # Handle different possible formats
    if isinstance(data, list):
        for item in data:
            segments.append({
                'speaker': item.get('speakerId', item.get('speaker', 'Unknown')),
                'start': item.get('startTimeSeconds', item.get('start', 0)),
                'end': item.get('endTimeSeconds', item.get('end', 0))
            })
    elif isinstance(data, dict):
        # May be wrapped in a 'segments' key
        items = data.get('segments', data.get('results', [data]))
        for item in items:
            segments.append({
                'speaker': item.get('speakerId', item.get('speaker', 'Unknown')),
                'start': item.get('startTimeSeconds', item.get('start', 0)),
                'end': item.get('endTimeSeconds', item.get('end', 0))
            })

    return sorted(segments, key=lambda x: x['start'])


def find_speaker_at_time(speaker_segments: list[dict], time: float) -> str:
    """Find which speaker was speaking at a given time."""
    for seg in speaker_segments:
        if seg['start'] <= time <= seg['end']:
            return seg['speaker']

    # If no exact match, find nearest speaker
    min_dist = float('inf')
    nearest_speaker = 'Unknown'
    for seg in speaker_segments:
        mid = (seg['start'] + seg['end']) / 2
        dist = abs(mid - time)
        if dist < min_dist:
            min_dist = dist
            nearest_speaker = seg['speaker']

    return nearest_speaker


def align_transcript(srt_segments: list[dict], speaker_segments: list[dict]) -> str:
    """Align transcript segments with speaker labels."""
    if not srt_segments:
        return ""

    lines = []
    current_speaker = None
    current_text = []

    for seg in srt_segments:
        # Use midpoint of segment to determine speaker
        mid_time = (seg['start'] + seg['end']) / 2
        speaker = find_speaker_at_time(speaker_segments, mid_time)

        if speaker != current_speaker:
            # Flush previous speaker's text
            if current_text and current_speaker:
                lines.append(f"**Speaker {current_speaker}:** {' '.join(current_text)}")
                lines.append("")
            current_speaker = speaker
            current_text = [seg['text']]
        else:
            current_text.append(seg['text'])

    # Flush final speaker
    if current_text and current_speaker:
        lines.append(f"**Speaker {current_speaker}:** {' '.join(current_text)}")

    return '\n'.join(lines)


def main():
    if len(sys.argv) < 4:
        print("Usage: align_speakers.py <srt_file> <fluidaudio_json> <output_md>")
        print("")
        print("Aligns Parakeet SRT transcript with FluidAudio speaker segments.")
        sys.exit(1)

    srt_path = sys.argv[1]
    json_path = sys.argv[2]
    output_path = sys.argv[3]

    # Validate inputs exist
    if not Path(srt_path).exists():
        print(f"Error: SRT file not found: {srt_path}")
        sys.exit(1)

    if not Path(json_path).exists():
        print(f"Error: FluidAudio JSON not found: {json_path}")
        sys.exit(1)

    # Parse inputs
    print(f"Parsing SRT: {srt_path}")
    srt_segments = parse_srt(srt_path)
    print(f"  Found {len(srt_segments)} transcript segments")

    print(f"Parsing FluidAudio JSON: {json_path}")
    speaker_segments = parse_fluidaudio_json(json_path)
    print(f"  Found {len(speaker_segments)} speaker segments")

    # Align
    print("Aligning transcript with speakers...")
    diarised_transcript = align_transcript(srt_segments, speaker_segments)

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(diarised_transcript)

    print(f"Diarised transcript written to: {output_path}")


if __name__ == '__main__':
    main()
