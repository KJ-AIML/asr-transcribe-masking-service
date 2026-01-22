import math
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.audio import chunk_wav_audio


def test_regions_to_segments_samples_floor_ceil():
    sr = 10
    total_samples = 100
    regions = [(0.0, 1.0001)]
    segments = chunk_wav_audio._regions_to_segments_samples(
        regions,
        sr,
        total_samples,
        min_speech_sec=0.0,
        max_segment_sec=10.0,
    )
    assert segments == [(0, int(math.ceil(1.0001 * sr)))]


def test_merge_regions_gap_threshold():
    regions = [(0.0, 1.0), (1.5, 2.0)]
    merged = chunk_wav_audio._merge_regions(regions, merge_gap_sec=0.6)
    assert merged == [(0.0, 2.0)]

    merged_none = chunk_wav_audio._merge_regions(regions, merge_gap_sec=None)
    assert merged_none == regions


def test_pad_regions_bounds():
    regions = [(0.2, 0.4)]
    padded = chunk_wav_audio._pad_regions(regions, pad_sec=0.5, total_duration=1.0)
    assert padded == [(0.0, 0.9)]
