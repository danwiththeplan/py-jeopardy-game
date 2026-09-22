#!/usr/bin/env python3
"""
Classroom Jeopardy - reads any question set from 3x3 up to 8x8.

Dependencies are managed with Poetry (see pyproject.toml). Install once with
`poetry install`, then run the game with `poetry run` in front of the usual
command:

    poetry run python jeopardy.py myset.csv
    poetry run python jeopardy.py myset.csv --check            # validate the file only
    poetry run python jeopardy.py myset.csv --teams "Kea,Weta" --time 45
    poetry run python jeopardy.py round1.csv,round2.csv,final.csv   # three rounds, in order
    poetry run python jeopardy.py myset.csv --ticktock ""      # no ticking clock

(If a `jeopardy` script entry point is defined in pyproject.toml, `poetry run
jeopardy myset.csv` works the same way, without "python" in front.)

While a question's timer is running, ticktock.wav (or the --ticktock file)
loops in the background, if it exists. It stops when the answer is revealed,
when time runs out, or when you leave the question. Sound files are looked
for in the current folder first, then in the folder this script is in.

Several rounds: give a comma-separated list of CSV files (no spaces, or quote
the whole list). Each file is a complete board in the format below, and the
boards can be different sizes. Scores carry over from round to round. When
every square of a round has been played, a "round complete" screen appears;
click or press ENTER to start the next round.

The CSV needs these five columns (extra columns are ignored):

    Row,Col,Question,Answer,Categories
    1,0,Some question,Some answer,First Category
    2,0,...,...,Second Category

Row 1 is the cheapest row (100 points), Row 2 is 200, and so on. Col is
zero-based and matches the order of the category names, which go one per
line down the Categories column of the first few lines. The board size is
taken from the file: the number of columns is the highest Col plus one,
the number of rows is the highest Row.

Controls:
        qset_human_origins.csv
        qset_plant_animal_responses.csv
    Click a team at the bottom            -> that team is answering
    Click a value on the board            -> question appears, timer starts
    Click the question / SPACE            -> reveal the answer
    CORRECT / WRONG buttons, or Y / N     -> score it and go back to the board
    Click another team while a question is up -> steals it for that team
    ESC back to the board   R restart timer   F fullscreen   Q quit
    END ROUND button (bottom right), click twice to confirm, or PAGE DOWN
                                          -> end this round early, go to the next
    FINISH GAME button (final round, or a single-round game), click twice,
    or PAGE DOWN                          -> go to the winner screen
The winner screen also appears by itself once the last square of the final
round has been played.
"""

import argparse
import csv
import os
import sys
import time

import pygame

MIN_SIDE, MAX_SIDE = 3, 8
REQUIRED_COLUMNS = ("Row", "Col", "Question", "Answer", "Categories")
POINTS_STEP = 100
MAX_TEAMS = 8
WIN_W, WIN_H = 1200, 820
CONFIRM_SECONDS = 3             # how long the END ROUND button waits for a second click
PAGE_DOWN_KEYS = (pygame.K_PAGEDOWN, pygame.K_KP3)       # KP3 = numpad PgDn, NumLock off
PAGE_DOWN_SCANCODES = (78, 91)  # SDL scancodes for PgDn and numpad 3, whatever the layout

BLUE = (6, 12, 180)
DARK = (10, 10, 40)
GOLD = (255, 204, 0)
WHITE = (255, 255, 255)
GREY = (120, 120, 130)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (20, 150, 60)


class QuestionFileError(Exception):
    """Raised when the CSV cannot be turned into a playable board."""


class Board(object):
    def __init__(self, categories, questions, n_rows, n_cols, path):
        self.categories = categories
        self.questions = questions
        self.n_rows = n_rows
        self.n_cols = n_cols
        self.path = path


# ------------------------------------------------------------- load/check --
def _problem_report(path, problems, note=None):
    lines = ["%s cannot be used as a question set:" % os.path.basename(path)]
    shown = problems[:12]
    lines += ["  - " + p for p in shown]
    if len(problems) > len(shown):
        lines.append("  ...and %d more" % (len(problems) - len(shown)))
    if note:
        lines.append("")
        lines.append(note)
    return "\n".join(lines)


def _read_rows(path):
    if not os.path.exists(path):
        raise QuestionFileError("No such file: %s" % path)
    if os.path.isdir(path):
        raise QuestionFileError("%s is a folder, not a CSV file." % path)
    if os.path.getsize(path) == 0:
        raise QuestionFileError("%s is empty." % path)
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            return reader.fieldnames or [], list(reader)
    except UnicodeDecodeError:
        raise QuestionFileError(
            "%s is not a plain-text CSV file.\nIf it is an .xlsx workbook, open it and "
            "use File > Save As > CSV UTF-8." % os.path.basename(path))
    except OSError as err:
        raise QuestionFileError("Could not read %s: %s" % (path, err))


def _column_map(path, fieldnames):
    found = {}
    for name in fieldnames:
        if name:
            found[name.strip().lower()] = name
    missing = [c for c in REQUIRED_COLUMNS if c.lower() not in found]
    if missing:
        raise QuestionFileError(
            "%s is missing the column%s %s.\n  Columns found: %s\n  Columns needed: %s"
            % (os.path.basename(path), "" if len(missing) == 1 else "s",
               ", ".join(missing),
               ", ".join(n for n in fieldnames if n) or "(none)",
               ", ".join(REQUIRED_COLUMNS)))
    return {c: found[c.lower()] for c in REQUIRED_COLUMNS}


def _whole_number(value):
    text = str(value if value is not None else "").strip()
    try:
        number = float(text)
    except ValueError:
        return None
    if number != int(number):
        return None
    return int(number)


def load_questions(path):
    """Read and validate a question set. Raises QuestionFileError with advice."""
    fieldnames, raw = _read_rows(path)
    columns = _column_map(path, fieldnames)
    get = lambda row, key: (row.get(columns[key]) or "").strip()

    problems = []
    questions = {}
    seen_on_line = {}
    categories = []

    for index, row in enumerate(raw):
        line = index + 2                      # +1 for the header, +1 for 1-based
        category = get(row, "Categories")
        if category:
            categories.append(category)
        if not any(get(row, c) for c in REQUIRED_COLUMNS):
            continue                          # blank line left by a spreadsheet
        question, answer = get(row, "Question"), get(row, "Answer")
        if not question and not answer:
            continue                          # a category-only line

        r = _whole_number(get(row, "Row"))
        c = _whole_number(get(row, "Col"))
        if r is None or r < 1:
            problems.append('line %d: Row must be a whole number of 1 or more (found "%s")'
                            % (line, get(row, "Row")))
            continue
        if c is None or c < 0:
            problems.append('line %d: Col must be a whole number of 0 or more (found "%s")'
                            % (line, get(row, "Col")))
            continue
        if not question:
            problems.append("line %d: Row %d, Col %d has no question" % (line, r, c))
            continue
        if not answer:
            problems.append("line %d: Row %d, Col %d has no answer" % (line, r, c))
            continue
        if (r, c) in questions:
            problems.append("line %d: Row %d, Col %d is already used on line %d"
                            % (line, r, c, seen_on_line[(r, c)]))
            continue
        seen_on_line[(r, c)] = line
        questions[(r, c)] = {"question": question, "answer": answer}

    if problems:
        raise QuestionFileError(_problem_report(path, problems))
    if not questions:
        raise QuestionFileError(
            "%s has no questions in it.\nEach line needs a Row, a Col, a Question and an "
            "Answer." % os.path.basename(path))

    n_rows = max(r for r, _ in questions)
    n_cols = max(c for _, c in questions) + 1

    size_note = ("This game handles boards from %dx%d to %dx%d. Columns come from the Col "
                 "column (0 upwards) and rows from the Row column (1 upwards)."
                 % (MIN_SIDE, MIN_SIDE, MAX_SIDE, MAX_SIDE))
    if not (MIN_SIDE <= n_rows <= MAX_SIDE) or not (MIN_SIDE <= n_cols <= MAX_SIDE):
        raise QuestionFileError(
            "%s describes a %d x %d board (%d rows, %d columns).\n%s"
            % (os.path.basename(path), n_rows, n_cols, n_rows, n_cols, size_note))

    if len(categories) != n_cols:
        # some people repeat the category on every line of a column - allow that
        unique = []
        for name in categories:
            if name not in unique:
                unique.append(name)
        if len(unique) == n_cols:
            categories = unique
    if len(categories) != n_cols:
        raise QuestionFileError(
            "%s has %d category name%s but the board is %d columns wide.\nPut exactly one "
            "category name per column, down the Categories column of the first %d lines."
            % (os.path.basename(path), len(categories),
               "" if len(categories) == 1 else "s", n_cols, n_cols))

    missing = [(r, c) for r in range(1, n_rows + 1) for c in range(n_cols)
               if (r, c) not in questions]
    if missing:
        raise QuestionFileError(_problem_report(
            path, ["no question for Row %d, Col %d (%s, %d points)"
                   % (r, c, categories[c], r * POINTS_STEP) for r, c in missing],
            note="A %d x %d board needs all %d squares filled in."
                 % (n_rows, n_cols, n_rows * n_cols)))

    return Board(categories, questions, n_rows, n_cols, path)


# ------------------------------------------------------------------- text --
_FONTS = {}


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


# ------------------------------------------------------------------- game --
class Game(object):
    def __init__(self, boards, teams, time_limit=30, buzzer="buzzer2.wav",
                 ticktock="ticktock.wav"):
        if isinstance(boards, Board):
            boards = [boards]
        self.boards = list(boards)
        self.round_index = 0
        self.teams = teams
        self.scores = [0] * len(teams)
        self.time_limit = time_limit
        self.buzzer = find_sound(buzzer)
        self.used = set()
        self.team_index = -1
        self.state = "board"            # board | question | answer | round_over | game_over
        self.current = None
        self.started = 0.0
        self.buzzed = False
        self.fullscreen = False
        self.confirm_until = 0.0        # END ROUND / FINISH GAME armed until then

        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error:
            pass
        self.ticktock = None                     # looped while the timer runs
        path = find_sound(ticktock)
        if path and pygame.mixer.get_init():
            try:
                self.ticktock = pygame.mixer.Sound(path)
            except pygame.error:
                pass
        self.ticking = False
        self.screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
        self.set_caption()
        self.w, self.h = self.screen.get_size()
        self.clock = pygame.time.Clock()

    # -- rounds ------------------------------------------------------------
    @property
    def board(self):
        return self.boards[self.round_index]

    @property
    def multi_round(self):
        return len(self.boards) > 1

    @property
    def has_next_round(self):
        return self.round_index + 1 < len(self.boards)

    def round_label(self, index=None):
        index = self.round_index if index is None else index
        return "Round %d of %d" % (index + 1, len(self.boards))

    def set_caption(self):
        name = os.path.basename(self.board.path)
        if self.multi_round:
            name = "%s - %s" % (self.round_label(), name)
        pygame.display.set_caption("Jeopardy - %s" % name)

    def round_finished(self):
        return len(self.used) >= self.board.n_rows * self.board.n_cols

    def end_round(self):
        """Leave the current round: on to the next one, or to the winner screen
        if this was the final round."""
        self.confirm_until = 0.0
        self.state = "round_over" if self.has_next_round else "game_over"
        self.current, self.team_index = None, -1

    def winners(self):
        best = max(self.scores)
        return [i for i, score in enumerate(self.scores) if score == best]

    def ranking(self):
        return sorted(range(len(self.teams)), key=lambda i: -self.scores[i])

    def is_page_down(self, event):
        return (event.key in PAGE_DOWN_KEYS
                or getattr(event, "scancode", None) in PAGE_DOWN_SCANCODES)

    def next_round(self):
        if not self.has_next_round:
            return
        self.round_index += 1
        self.used = set()
        self.state, self.current, self.team_index = "board", None, -1
        self.set_caption()

    # -- geometry ----------------------------------------------------------
    @property
    def score_h(self):
        return int(min(150, max(80, self.h * 0.17)))

    @property
    def board_h(self):
        return self.h - self.score_h

    @property
    def cell_w(self):
        return self.w / float(self.board.n_cols)

    @property
    def band_h(self):
        return self.board_h / float(self.board.n_rows + 1)

    def cell_at(self, pos):
        col = int(pos[0] // self.cell_w)
        band = int(pos[1] // self.band_h)
        if band < 1 or band > self.board.n_rows or col >= self.board.n_cols:
            return None
        return (band, col)

    def end_round_rect(self):
        """The END ROUND / FINISH GAME button at the right of the score bar,
        or None on screens that have no score bar."""
        if self.state in ("round_over", "game_over"):
            return None
        width = int(min(190, max(110, self.w * 0.13)))
        return pygame.Rect(self.w - width + 4, self.board_h + 4, width - 8, self.score_h - 8)

    @property
    def teams_w(self):
        button = self.end_round_rect()
        return self.w - (button.w + 8 if button else 0)

    def team_at(self, pos):
        if pos[1] < self.board_h or pos[0] >= self.teams_w:
            return None
        return min(int(pos[0] // (self.teams_w / float(len(self.teams)))), len(self.teams) - 1)

    def button_rects(self):
        w, h = self.w / 4.0, 80
        y = self.board_h - 110
        return ((self.w / 8.0, y, w, h), (self.w * 5 / 8.0, y, w, h))

    @staticmethod
    def points(row):
        return row * POINTS_STEP

    # -- drawing -----------------------------------------------------------
    def draw_score_bar(self):
        pygame.draw.rect(self.screen, DARK, (0, self.board_h, self.w, self.score_h))
        width = self.teams_w / float(len(self.teams))
        for i, name in enumerate(self.teams):
            box = pygame.Rect(i * width + 4, self.board_h + 4, width - 8, self.score_h - 8)
            pygame.draw.rect(self.screen, BLUE if i == self.team_index else DARK, box)
            pygame.draw.rect(self.screen, GOLD if i == self.team_index else GREY, box, 3)
            draw_text(self.screen, name, (box.x, box.y + 6, box.w, box.h * 0.40),
                      WHITE, 30, 11, True)
            draw_text(self.screen, str(self.scores[i]),
                      (box.x, box.y + box.h * 0.42, box.w, box.h * 0.52), GOLD, 46, 14, True)
        button = self.end_round_rect()
        if button:
            armed = time.perf_counter() < self.confirm_until
            pygame.draw.rect(self.screen, RED if armed else DARK, button)
            pygame.draw.rect(self.screen, RED, button, 3)
            action = "END ROUND" if self.has_next_round else "FINISH GAME"
            draw_text(self.screen, "CLICK AGAIN TO " + action if armed else action,
                      (button.x, button.y, button.w, button.h), WHITE, 26, 10, True)

    def draw_board(self):
        self.screen.fill(BLACK)
        for col in range(self.board.n_cols):
            head = pygame.Rect(col * self.cell_w + 3, 3, self.cell_w - 6, self.band_h - 6)
            pygame.draw.rect(self.screen, DARK, head)
            draw_text(self.screen, self.board.categories[col].upper(),
                      (head.x, head.y, head.w, head.h), GOLD, 34, 10, True)
            for row in range(1, self.board.n_rows + 1):
                box = pygame.Rect(col * self.cell_w + 3, row * self.band_h + 3,
                                  self.cell_w - 6, self.band_h - 6)
                used = (row, col) in self.used
                pygame.draw.rect(self.screen, DARK if used else BLUE, box)
                if not used:
                    draw_text(self.screen, str(self.points(row)),
                              (box.x, box.y, box.w, box.h), GOLD, 64, 14, True)
        self.draw_score_bar()

    def draw_round_over(self):
        self.screen.fill(BLUE)
        top = self.board_h
        draw_text(self.screen, "Round %d complete" % (self.round_index + 1),
                  (40, top * 0.12, self.w - 80, top * 0.22), GOLD, 80, 24, True)
        leader = max(range(len(self.teams)), key=lambda i: self.scores[i])
        draw_text(self.screen, "Leading: %s (%d)" % (self.teams[leader], self.scores[leader]),
                  (40, top * 0.38, self.w - 80, top * 0.14), WHITE, 46, 16, True)
        draw_text(self.screen, "Next up: %s" % self.round_label(self.round_index + 1),
                  (40, top * 0.56, self.w - 80, top * 0.14), GOLD, 46, 16, True)
        draw_text(self.screen, "click or press ENTER to start the next round",
                  (0, top - 50, self.w, 40), WHITE, 24, 12)
        self.draw_score_bar()

    def draw_game_over(self):
        self.screen.fill(BLACK)
        winners = self.winners()
        names = " & ".join(self.teams[i] for i in winners)
        title_h = self.h * 0.30
        draw_text(self.screen, "GAME OVER", (0, self.h * 0.03, self.w, title_h * 0.30),
                  WHITE, 44, 16, True)
        draw_text(self.screen, "IT'S A TIE!" if len(winners) > 1 else "WINNER",
                  (0, title_h * 0.33, self.w, title_h * 0.22), GOLD, 40, 14, True)
        draw_text(self.screen, names, (40, title_h * 0.55, self.w - 80, title_h * 0.45),
                  GOLD, 90, 20, True)

        order = self.ranking()
        top = title_h + 20
        room = self.h - top - 50
        row_h = min(80, room / float(len(order)))
        table_w = min(self.w - 80, 800)
        left = (self.w - table_w) / 2.0
        place, previous = 0, None
        for n, i in enumerate(order):
            if self.scores[i] != previous:        # equal scores share a place
                place, previous = n + 1, self.scores[i]
            won = i in winners
            box = pygame.Rect(left, top + n * row_h + 3, table_w, row_h - 6)
            pygame.draw.rect(self.screen, GOLD if won else DARK, box)
            pygame.draw.rect(self.screen, WHITE if won else GREY, box, 3)
            ink = BLACK if won else WHITE
            draw_text(self.screen, "%d" % place, (box.x, box.y, box.w * 0.12, box.h),
                      ink, 44, 12, True)
            draw_text(self.screen, self.teams[i],
                      (box.x + box.w * 0.12, box.y, box.w * 0.60, box.h), ink, 44, 12, True)
            draw_text(self.screen, str(self.scores[i]),
                      (box.x + box.w * 0.72, box.y, box.w * 0.28, box.h),
                      BLACK if won else GOLD, 44, 12, True)
        draw_text(self.screen, "press Q to quit", (0, self.h - 42, self.w, 34), GREY, 22, 12)

    def draw_question(self):
        self.screen.fill(BLUE)
        row, col = self.current
        item = self.board.questions.get(
            self.current, {"question": "No question for this square.", "answer": "-"})
        name = self.board.categories[col] if col < len(self.board.categories) else ""
        top = self.board_h
        draw_text(self.screen, "%s  -  %d points" % (name, self.points(row)),
                  (0, 20, self.w, 46), GOLD, 34, 14, True)
        draw_text(self.screen, item["question"],
                  (60, top * 0.13, self.w - 120, top * 0.40), WHITE, 54, 16, True)

        if self.state == "question":
            left = self.time_left()
            colour = RED if left <= 5 else GOLD
            draw_text(self.screen, "TIME UP" if left == 0 else "%0.0f" % left,
                      (0, top * 0.62, self.w, top * 0.16), colour, 80, 24, True)
            draw_text(self.screen, "click anywhere or press SPACE to reveal the answer",
                      (0, top - 50, self.w, 40), WHITE, 24, 12)
            if left == 0 and not self.buzzed:
                self.buzz()
        else:
            draw_text(self.screen, item["answer"],
                      (60, top * 0.55, self.w - 120, top * 0.26), GOLD, 46, 14, True)
            right, wrong = self.button_rects()
            pygame.draw.rect(self.screen, GREEN, right)
            pygame.draw.rect(self.screen, RED, wrong)
            draw_text(self.screen, "CORRECT  +%d" % self.points(row), right, WHITE, 30, 12, True)
            draw_text(self.screen, "WRONG  -%d" % self.points(row), wrong, WHITE, 30, 12, True)
        self.draw_score_bar()

    # -- actions -----------------------------------------------------------
    def time_left(self):
        return max(0, self.time_limit - (time.perf_counter() - self.started))

    def update_ticktock(self):
        """Tick while a question is up and the clock is running, and at no
        other time. Called every frame, so every way of leaving a question
        (reveal, ESC, time up, ending the round) stops the sound."""
        if self.ticktock is None:
            return
        wanted = self.state == "question" and self.time_left() > 0
        if wanted and not self.ticking:
            self.ticktock.play(loops=-1)
        elif not wanted and self.ticking:
            self.ticktock.stop()
        self.ticking = wanted

    def buzz(self):
        self.buzzed = True
        if pygame.mixer.get_init() and self.buzzer and os.path.exists(self.buzzer):
            try:
                pygame.mixer.music.load(self.buzzer)
                pygame.mixer.music.play()
            except pygame.error:
                pass

    def open_cell(self, cell):
        if cell in self.used or self.team_index < 0:
            return
        self.used.add(cell)
        self.current = cell
        self.state = "question"
        self.started = time.perf_counter()
        self.buzzed = False

    def score(self, correct):
        row, _ = self.current
        if self.team_index >= 0:
            self.scores[self.team_index] += self.points(row) * (1 if correct else -1)
        self.state, self.current, self.team_index = "board", None, -1

    def resize(self, size):
        self.w, self.h = max(640, size[0]), max(480, size[1])
        self.screen = pygame.display.set_mode((self.w, self.h), pygame.RESIZABLE)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
        self.w, self.h = self.screen.get_size()

    # -- loop --------------------------------------------------------------
    def handle(self, event):
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.VIDEORESIZE:
            self.resize((event.w, event.h))
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q:
                return False
            if event.key == pygame.K_f:
                self.toggle_fullscreen()
            elif self.state == "round_over" and event.key in (
                    pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.next_round()
            elif self.state in ("round_over", "game_over"):
                pass                              # only the keys above work here
            elif self.is_page_down(event):
                self.end_round()
            elif event.key == pygame.K_ESCAPE:
                self.state, self.current, self.team_index = "board", None, -1
            elif event.key == pygame.K_r and self.state == "question":
                self.started, self.buzzed = time.perf_counter(), False
            elif event.key == pygame.K_SPACE and self.state == "question":
                self.state = "answer"
            elif event.key == pygame.K_y and self.state == "answer":
                self.score(True)
            elif event.key == pygame.K_n and self.state == "answer":
                self.score(False)
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.state == "round_over":
                if event.pos[1] < self.board_h:
                    self.next_round()
                return True
            if self.state == "game_over":
                return True
            button = self.end_round_rect()
            if button and button.collidepoint(event.pos):
                if time.perf_counter() < self.confirm_until:
                    self.end_round()
                else:
                    self.confirm_until = time.perf_counter() + CONFIRM_SECONDS
                return True
            team = self.team_at(event.pos)
            if team is not None:
                self.team_index = team
                if self.state == "question":
                    self.started, self.buzzed = time.perf_counter(), False
                return True
            if self.state == "board":
                cell = self.cell_at(event.pos)
                if cell:
                    self.open_cell(cell)
            elif self.state == "question":
                self.state = "answer"
            elif self.state == "answer":
                right, wrong = self.button_rects()
                if pygame.Rect(right).collidepoint(event.pos):
                    self.score(True)
                elif pygame.Rect(wrong).collidepoint(event.pos):
                    self.score(False)
        return True

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                running = self.handle(event) and running
            if self.state == "board" and self.round_finished():
                self.end_round()
            if self.state == "board":
                self.draw_board()
            elif self.state == "round_over":
                self.draw_round_over()
            elif self.state == "game_over":
                self.draw_game_over()
            else:
                self.draw_question()
            self.update_ticktock()
            pygame.display.update()
            self.clock.tick(30)
        pygame.quit()
        print("\nFinal scores")
        winners = self.winners()
        for i in self.ranking():
            print("  %-20s %5d%s" % (self.teams[i], self.scores[i],
                                     "   <- winner" if i in winners else ""))


# ------------------------------------------------------------------- main --
def find_sound(name):
    """Return a path for the sound file `name`, looking in the current folder
    and then next to this script. None if it is not found or not wanted."""
    if not name:
        return None
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (name, os.path.join(here, name)):
        if os.path.isfile(path):
            return path
    return None


def ask_teams():
    while True:
        try:
            count = int(input("Number of teams (1-%d): " % MAX_TEAMS))
        except ValueError:
            count = 0
        if 1 <= count <= MAX_TEAMS:
            break
        print("Please enter a number between 1 and %d." % MAX_TEAMS)
    names = []
    for i in range(count):
        name = input("Team %d name: " % (i + 1)).strip()
        names.append(name or "Team %d" % (i + 1))
    return names


def parse_teams(text):
    names = [n.strip() for n in text.split(",") if n.strip()]
    if not 1 <= len(names) <= MAX_TEAMS:
        raise QuestionFileError("Give between 1 and %d team names, separated by commas."
                                % MAX_TEAMS)
    return names


def parse_csv_list(text):
    paths = [p.strip() for p in text.split(",") if p.strip()]
    if not paths:
        raise QuestionFileError("Give at least one CSV file.")
    return paths


def load_rounds(paths):
    """Load every round, collecting problems from all files before giving up."""
    boards, errors = [], []
    for number, path in enumerate(paths, 1):
        try:
            boards.append(load_questions(path))
        except QuestionFileError as err:
            prefix = "Round %d: " % number if len(paths) > 1 else ""
            errors.append(prefix + str(err))
    if errors:
        raise QuestionFileError("\n\n".join(errors))
    return boards


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Classroom Jeopardy. The board size (%dx%d to %dx%d) is read from the CSV."
                    % (MIN_SIDE, MIN_SIDE, MAX_SIDE, MAX_SIDE))
    parser.add_argument("csv_files", metavar="CSV[,CSV...]",
                        help="question set, e.g. myset.csv; for several rounds give a "
                             "comma-separated list, played in order, e.g. r1.csv,r2.csv")
    parser.add_argument("--teams", help='team names, e.g. --teams "Kea,Weta,Tuatara"')
    parser.add_argument("--time", type=int, default=30, metavar="SECONDS",
                        help="seconds allowed per question (default 30)")
    parser.add_argument("--buzzer", default="buzzer2.wav", metavar="WAV",
                        help="sound played at time up, if the file exists")
    parser.add_argument("--ticktock", default="ticktock.wav", metavar="WAV",
                        help="sound looped while the timer runs, if the file exists "
                             '(default ticktock.wav; --ticktock "" for silence)')
    parser.add_argument("--check", action="store_true",
                        help="check the CSV and print a summary without starting the game")
    args = parser.parse_args(argv)

    try:
        boards = load_rounds(parse_csv_list(args.csv_files))
        teams = parse_teams(args.teams) if args.teams else None
    except QuestionFileError as err:
        sys.stderr.write("\n%s\n\n" % err)
        return 2

    if args.check:
        for number, board in enumerate(boards, 1):
            prefix = "Round %d: " % number if len(boards) > 1 else ""
            print("%s%s looks good: %d x %d board, %d questions, %d points at the top."
                  % (prefix, os.path.basename(board.path), board.n_rows, board.n_cols,
                     len(board.questions), board.n_rows * POINTS_STEP))
            for i, name in enumerate(board.categories):
                print("  Col %d: %s" % (i, name))
        return 0

    if teams is None:
        teams = ask_teams()
    Game(boards, teams, time_limit=max(5, args.time), buzzer=args.buzzer,
         ticktock=args.ticktock).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
