#!/usr/bin/env python3
"""
Merge FluidAudio speaker diarisation results from multiple chunks.

Handles:
- Timestamp adjustment (adding chunk offsets)
- Speaker ID reconciliation across chunks using embedding similarity
- Overlap deduplication
"""

import json
import argparse
import numpy as np
from pathlib import Path
from typing import List, Dict, Any


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def get_speaker_centroids(segments: List[Dict]) -> Dict[str, np.ndarray]:
    """Compute average embedding for each speaker."""
    speaker_embeddings: Dict[str, List[List[float]]] = {}
    for seg in segments:
        sid = seg['speakerId']
        if sid not in speaker_embeddings:
            speaker_embeddings[sid] = []
        speaker_embeddings[sid].append(seg['embedding'])

    centroids = {}
    for sid, embeddings in speaker_embeddings.items():
        centroids[sid] = np.mean(embeddings, axis=0)
    return centroids


def map_speakers(
    new_centroids: Dict[str, np.ndarray],
    existing_centroids: Dict[str, np.ndarray],
    threshold: float = 0.85
) -> Dict[str, str]:
    """
    Map speaker IDs from new chunk to existing speakers.
    Returns mapping from new_id -> existing_id (or new unique ID if no match).
    """
    mapping = {}
    next_id = max(int(sid) for sid in existing_centroids.keys()) + 1 if existing_centroids else 1

    for new_sid, new_centroid in new_centroids.items():
        best_match = None
        best_sim = threshold

        for existing_sid, existing_centroid in existing_centroids.items():
            sim = cosine_similarity(new_centroid, existing_centroid)
            if sim > best_sim:
                best_sim = sim
                best_match = existing_sid

        if best_match:
            mapping[new_sid] = best_match
        else:
            # New speaker not seen before
            mapping[new_sid] = str(next_id)
            next_id += 1

    return mapping


def merge_chunks(
    chunk_files: List[Path],
    chunk_offsets: List[float],
    chunk_size: float,
    overlap: float
) -> Dict[str, Any]:
    """Merge multiple FluidAudio JSON outputs into one."""

    all_segments = []
    global_centroids: Dict[str, np.ndarray] = {}
    total_duration = 0

    for i, (chunk_file, offset) in enumerate(zip(chunk_files, chunk_offsets)):
        with open(chunk_file) as f:
            data = json.load(f)

        segments = data['segments']
        if not segments:
            continue

        # Get centroids for this chunk
        chunk_centroids = get_speaker_centroids(segments)

        # Map speakers to global IDs
        if i == 0:
            # First chunk - speakers become global
            speaker_map = {sid: sid for sid in chunk_centroids.keys()}
            global_centroids = chunk_centroids.copy()
        else:
            # Map to existing speakers
            speaker_map = map_speakers(chunk_centroids, global_centroids)

            # Update global centroids with new speakers
            for new_sid, global_sid in speaker_map.items():
                if global_sid not in global_centroids:
                    global_centroids[global_sid] = chunk_centroids[new_sid]

        # Process segments
        for seg in segments:
            start = seg['startTimeSeconds'] + offset
            end = seg['endTimeSeconds'] + offset

            # Skip segments in overlap region that duplicate previous chunk
            if i > 0 and start < chunk_offsets[i - 1] + chunk_size:
                continue

            new_seg = {
                'startTimeSeconds': start,
                'endTimeSeconds': end,
                'speakerId': speaker_map[seg['speakerId']],
                'qualityScore': seg['qualityScore'],
                'embedding': seg['embedding']
            }
            all_segments.append(new_seg)

        total_duration = max(total_duration, data['durationSeconds'] + offset)

    # Sort by start time
    all_segments.sort(key=lambda x: x['startTimeSeconds'])

    # Build output
    result = {
        'audioFile': 'merged',
        'config': {'merged': True, 'chunks': len(chunk_files)},
        'durationSeconds': total_duration,
        'segments': all_segments,
        'speakerCount': len(global_centroids),
        'timestamp': chunk_files[0].stat().st_mtime if chunk_files else 0
    }

    return result


def main():
    parser = argparse.ArgumentParser(description='Merge FluidAudio chunk outputs')
    parser.add_argument('output', type=Path, help='Output JSON file')
    parser.add_argument('--chunks', type=Path, nargs='+', required=True,
                        help='Input chunk JSON files in order')
    parser.add_argument('--chunk-size', type=float, default=3600,
                        help='Chunk size in seconds (default: 3600)')
    parser.add_argument('--overlap', type=float, default=30,
                        help='Overlap between chunks in seconds (default: 30)')

    args = parser.parse_args()

    # Calculate offsets
    offsets = [i * args.chunk_size for i in range(len(args.chunks))]

    result = merge_chunks(args.chunks, offsets, args.chunk_size, args.overlap)

    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"Merged {len(args.chunks)} chunks")
    print(f"Total segments: {len(result['segments'])}")
    print(f"Speakers found: {result['speakerCount']}")
    print(f"Output: {args.output}")


if __name__ == '__main__':
    main()
