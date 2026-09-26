import os

import pygame
import pytest

from jeopardy.utils import draw_picture, find_sound, get_font, whole_number, wrap


# ------------------------------------------------------------------ whole_number --
@pytest.mark.parametrize(
    "value, expected",
    [
        ("5", 5),
        ("5.0", 5),
        (5, 5),
        (" 7 ", 7),
        ("-3", -3),
        ("5.5", None),
        ("abc", None),
        ("", None),
        (None, None),
    ],
)
def test_whole_number(value, expected):
    assert whole_number(value) == expected


# --------------------------------------------------------------------- find_sound --
def test_find_sound_prefers_current_folder(tmp_path, monkeypatch):
    local = tmp_path / "buzzer2.wav"
    local.write_bytes(b"")
    monkeypatch.chdir(tmp_path)
    assert find_sound("buzzer2.wav") == "buzzer2.wav"


def test_find_sound_falls_back_to_package_resources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    found = find_sound("buzzer2.wav")
    assert found is not None
    assert os.path.basename(found) == "buzzer2.wav"
    assert "resources" in found


def test_find_sound_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert find_sound("no-such-sound.wav") is None


def test_find_sound_empty_name_returns_none():
    assert find_sound("") is None
    assert find_sound(None) is None


# --------------------------------------------------------------------------- wrap --
def test_wrap_keeps_short_text_on_one_line():
    font = get_font(20)
    lines = wrap(font, "short text", 1000)
    assert lines == ["short text"]


def test_wrap_breaks_long_text_into_multiple_lines():
    font = get_font(20)
    text = " ".join(["word"] * 30)
    narrow_width = font.size("word word")[0]
    lines = wrap(font, text, narrow_width)
    assert len(lines) > 1
    assert all(font.size(line)[0] <= narrow_width for line in lines)


def test_wrap_hard_breaks_overlong_word():
    font = get_font(20)
    long_word = "a" * 200
    narrow_width = font.size("aaaa")[0]
    lines = wrap(font, long_word, narrow_width, hard=True)
    assert len(lines) > 1
    assert "".join(lines) == long_word


# ------------------------------------------------------------------- draw_picture --
def test_draw_picture_fits_inside_rect_keeping_shape(tmp_path):
    path = str(tmp_path / "wide.png")
    picture = pygame.Surface((400, 100))
    picture.fill((255, 0, 0))
    pygame.image.save(picture, path)

    target = pygame.Surface((300, 300))
    assert draw_picture(target, path, (0, 0, 200, 200)) is True
    # 400x100 scaled to 200x50, centred vertically: rows 75-124 are red
    assert target.get_at((100, 100))[:3] == (255, 0, 0)
    assert target.get_at((100, 60))[:3] == (0, 0, 0)
    assert target.get_at((250, 100))[:3] == (0, 0, 0)


def test_draw_picture_unreadable_file_draws_nothing(tmp_path):
    path = tmp_path / "broken.png"
    path.write_bytes(b"not a png")
    assert draw_picture(pygame.Surface((50, 50)), str(path), (0, 0, 50, 50)) is False
