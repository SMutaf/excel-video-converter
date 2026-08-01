"""Kare dizisi -> mozaik ve ayar dogrulama."""

from __future__ import annotations

import numpy as np
import pytest

from excelvid import convert, pipeline, video


def test_mosaic_shapes_and_bounds(frames_rgb):
    m = pipeline.build(frames_rgb, cols=16, colors=8)
    assert m.n_frames == len(frames_rgb)
    assert m.fill_idx.shape == m.font_idx.shape == m.char_idx.shape
    assert m.fill_idx.shape == (len(frames_rgb), m.rows, m.cols)
    assert m.fill_idx.max() < len(m.palette)
    assert m.font_idx.max() < len(m.palette)
    assert m.char_idx.max() < len(m.chars)


def test_palette_is_shared_across_frames(frames_rgb):
    """Palet tum karelerden bir kez cikmali.

    Kare basina palet cikarilsaydi sabit duran bolgelerin rengi kareler arasi
    titrerdi; burada zemin sabit beyaz oldugu icin ayni indekse dusmeli.
    """
    m = pipeline.build(frames_rgb, cols=16, colors=8)
    corner = m.fill_idx[:, 0, 0]
    assert len(np.unique(corner)) == 1


def test_build_rejects_empty():
    with pytest.raises(ValueError):
        pipeline.build([], cols=16)


def test_progress_tick_is_monotonic(frames_rgb):
    seen: list[float] = []
    pipeline.build(frames_rgb, cols=16, colors=8, tick=lambda d, t: seen.append(d / t))
    assert seen and seen[-1] == pytest.approx(1.0)
    assert all(b >= a for a, b in zip(seen, seen[1:]))


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("cols", 5000, 200),
        ("cols", 1, 16),
        ("colors", 99, 32),
        ("colors", 0, 2),
        ("sub", 99, 12),
        ("max_frames", -10, 0),
    ],
)
def test_settings_are_clamped(field, value, expected):
    settings, notes = convert.Settings(**{field: value}).clamped()
    assert getattr(settings, field) == expected
    assert any(field in n for n in notes)


def test_settings_within_range_are_untouched():
    settings, notes = convert.Settings(cols=64, colors=32, sub=4).clamped()
    assert notes == []
    assert (settings.cols, settings.colors, settings.sub) == (64, 32, 4)


@pytest.mark.parametrize(
    "crop_width,sub,expected",
    [(311, 4, 77), (311, 6, 51), (311, 8, 38), (100, 4, 25)],
)
def test_max_supported_cols(crop_width, sub, expected):
    assert convert.max_supported_cols(crop_width, sub) == expected


def test_probe_reads_synthetic_video(sample_video):
    info = video.probe(sample_video)
    assert info.width == 96 and info.height == 72
    assert info.frame_count == 12
    assert info.fps == pytest.approx(12.0, abs=0.5)


def test_analyze_finds_moving_subject(sample_video):
    analysis = convert.analyze(sample_video, convert.Settings(autocrop=True))
    assert analysis.box is not None
    # Ozne yatayda 8..8+11*4+20 arasinda geziyor, dikeyde sabit bir serit
    assert analysis.box.width > analysis.box.height
    assert analysis.box.height < 72


def test_analyze_rejects_non_video(tmp_path):
    bad = tmp_path / "not_a_video.mp4"
    bad.write_bytes(b"definitely not a video")
    with pytest.raises(convert.UnreadableVideoError):
        convert.analyze(bad, convert.Settings(autocrop=False))


def test_analyze_rejects_missing_file(tmp_path):
    with pytest.raises(convert.UnreadableVideoError):
        convert.analyze(tmp_path / "nope.mp4", convert.Settings(autocrop=False))
