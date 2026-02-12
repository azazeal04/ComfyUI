from comfy_execution.media_engines import AudioEngine, ImageEngine, VideoEngine


def test_image_engine_tiles_cover_area():
    engine = ImageEngine()
    tiles = engine.plan_tiles(1024, 768, 512)
    assert len(tiles) > 0
    assert tiles[0].width > 0 and tiles[0].height > 0


def test_video_engine_windows_non_empty():
    engine = VideoEngine()
    windows = engine.plan_windows(24)
    assert len(windows) > 0
    assert windows[0][0] == 0


def test_audio_engine_segments_non_empty():
    engine = AudioEngine()
    segments = engine.plan_segments(96000)
    assert len(segments) > 0
    assert segments[0][1] > segments[0][0]
