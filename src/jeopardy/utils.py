"""Generic helpers used by the game: number parsing, sound lookup, and the
pygame text-fitting and picture-fitting routines used to draw everything on
the board."""

import os

import pygame

_FONTS = {}
_PICTURES = {}          # path -> loaded image, or None if it could not be loaded
_SCALED = {}            # (path, width, height) -> image scaled to fit that box


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


def load_picture(path):
    """Load the image at `path` once and keep it. None if it can't be loaded."""
    if path not in _PICTURES:
        try:
            image = pygame.image.load(path)
            if pygame.display.get_surface() is not None:
                image = image.convert_alpha()
        except (pygame.error, OSError):
            image = None
        _PICTURES[path] = image
    return _PICTURES[path]


def draw_picture(surface, path, rect):
    """Draw the picture at `path` as large as it fits inside `rect`, keeping
    its shape, centred. Returns False (and draws nothing) if it can't be loaded."""
    image = load_picture(path)
    x, y, w, h = [int(v) for v in rect]
    if image is None or w < 1 or h < 1:
        return False
    key = (path, w, h)
    if key not in _SCALED:
        scale = min(w / float(image.get_width()), h / float(image.get_height()))
        size = (max(1, int(image.get_width() * scale)), max(1, int(image.get_height() * scale)))
        try:
            _SCALED[key] = pygame.transform.smoothscale(image, size)
        except ValueError:                        # smoothscale needs 24/32-bit images
            _SCALED[key] = pygame.transform.scale(image, size)
    scaled = _SCALED[key]
    surface.blit(scaled, (x + (w - scaled.get_width()) // 2, y + (h - scaled.get_height()) // 2))
    return True


def get_font(size, bold=False):
    if (size, bold) not in _FONTS:
        _FONTS[(size, bold)] = pygame.font.SysFont("Arial", size, bold=bold)
    return _FONTS[(size, bold)]


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
