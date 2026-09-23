"""Generic helpers used by the game: number parsing, sound lookup, and the
pygame text-fitting routines used to draw everything on the board."""

import os

import pygame

_FONTS = {}


def whole_number(value):
    """Parse `value` as a whole number, or None if it isn't one."""
    text = str(value if value is not None else "").strip()
    try:
        number = float(text)
    except ValueError:
        return None
    if number != int(number):
        return None
    return int(number)


def find_sound(name):
    """Return a path for the sound file `name`, looking in the current folder
    and then in this package's resources folder. None if it is not found or
    not wanted."""
    if not name:
        return None
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")
    for path in (name, os.path.join(here, name)):
        if os.path.isfile(path):
            return path
    return None


def get_font(size, bold=False):
    if (size, bold) not in _FONTS:
        _FONTS[(size, bold)] = pygame.font.SysFont("Arial", size, bold=bold)
    return _FONTS[(size, bold)]


def forget_fonts():
    """Drop cached fonts; they are unusable once pygame.quit() has run."""
    _FONTS.clear()


def wrap(font, text, max_w, hard=False):
    """Split `text` into lines that fit `max_w`. With hard=True, over-long
    words are broken mid-word rather than allowed to overflow."""
    lines, current = [], ""
    for word in str(text).split():
        while hard and font.size(word)[0] > max_w and len(word) > 1:
            cut = len(word)
            while cut > 1 and font.size(word[:cut])[0] > max_w:
                cut -= 1
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:cut])
            word = word[cut:]
        trial = (current + " " + word).strip()
        if current and font.size(trial)[0] > max_w:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def draw_text(surface, text, rect, colour, max_size=52, min_size=14, bold=False):
    """Fit `text` inside `rect`, shrinking the font until it fits."""
    x, y, w, h = rect
    inner = w - 16
    font, lines, line_h = None, [], 0
    for size in range(int(max_size), int(min_size) - 1, -2):
        font = get_font(size, bold)
        lines = wrap(font, text, inner)
        line_h = font.get_linesize()
        widest = max([font.size(line)[0] for line in lines] or [0])
        if widest <= inner and len(lines) * line_h <= h:
            break
    else:
        # nothing fits even at the smallest size - break words to stay inside
        font = get_font(int(min_size), bold)
        lines = wrap(font, text, inner, hard=True)
        line_h = font.get_linesize()
    top = y + (h - len(lines) * line_h) / 2
    for i, line in enumerate(lines):
        image = font.render(line, True, colour)
        surface.blit(image, (x + (w - image.get_width()) / 2, top + i * line_h))
