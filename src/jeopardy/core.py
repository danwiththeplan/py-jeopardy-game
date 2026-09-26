"""
Classroom Jeopardy - reads any question set from 3x3 up to 8x8.

    jeopardy myset.csv
    jeopardy myset.csv --check            # validate the file only
    jeopardy myset.csv --teams "Kea,Weta" --time 45
    jeopardy round1.csv,round2.csv,final.csv   # three rounds, in order
    jeopardy myset.csv --ticktock ""      # no ticking clock
    jeopardy myset.csv --buzzer ""        # no buzzer
    jeopardy myset.csv --mode savage      # penalties on, steals worth full points

Scoring modes (--mode, default nice):
    nice    a wrong answer costs nothing; a steal earns half the points
    savage  a wrong answer costs the full value; a steal earns the full points

Steals: the team that picked the square answers. If they are marked WRONG
on the answer screen, a steal screen follows: click every other team that got
it right (click again to un-select), then AWARD STEALS (or ENTER) gives them
all the steal points at once.

While a question's timer is running, ticktock.wav (or the --ticktock file)
loops in the background, if it exists. It stops when the answer is revealed,
when time runs out, or when you leave the question. Sound files are looked
for in the current folder first, then in this package's resources folder.

Several rounds: give a comma-separated list of CSV files (no spaces, or quote
the whole list). Each file is a complete board in the format below, and the
boards can be different sizes. Scores carry over from round to round. When
every square of a round has been played, a "round complete" screen appears;
click or press ENTER to start the next round.

The CSV needs these five columns (extra columns are ignored):

    Row,Col,Question,Answer,Categories
    1,0,Some question,Some answer,First Category
    2,0,...,...,Second Category

An optional Picture column gives the path of a PNG or JPG file to show above
the question (a relative path is taken from the CSV file's folder). Leave it
blank for questions without a picture. A picture that is missing or not a
PNG/JPG gives a warning, and the question is shown without it.

Row 1 is the cheapest row (100 points), Row 2 is 200, and so on. Col is
zero-based and matches the order of the category names, which go one per
line down the Categories column of the first few lines. The board size is
taken from the file: the number of columns is the highest Col plus one,
the number of rows is the highest Row.

Controls:
    Click a team at the bottom            -> that team is answering
    Click a value on the board            -> question appears, timer starts
    Click the question / SPACE            -> reveal the answer
    P                                      -> pause / resume the timer
    CORRECT / WRONG buttons, or Y / N     -> score the team that picked the square
    Steal screen: click teams, then AWARD STEALS / ENTER -> steal points for all of them
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

from jeopardy.utils import draw_picture, draw_text, find_sound, whole_number

MIN_SIDE, MAX_SIDE = 3, 8
REQUIRED_COLUMNS = ("Row", "Col", "Question", "Answer", "Categories")
OPTIONAL_COLUMNS = ("Picture",)
PICTURE_TYPES = (".png", ".jpg", ".jpeg")
POINTS_STEP = 100
MAX_TEAMS = 8
MODES = ("nice", "savage")
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
    def __init__(self, categories, questions, n_rows, n_cols, path, warnings=()):
        self.categories = categories
        self.questions = questions
        self.n_rows = n_rows
        self.n_cols = n_cols
        self.path = path
        self.warnings = list(warnings)     # problems that don't stop the game


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
    return {c: found[c.lower()] for c in REQUIRED_COLUMNS + OPTIONAL_COLUMNS
            if c.lower() in found}


def _picture_path(csv_path, text):
    """The picture file named in the Picture column. A relative path is taken
    from the CSV file's folder."""
    picture = os.path.expanduser(text)
    if not os.path.isabs(picture):
        picture = os.path.join(os.path.dirname(os.path.abspath(csv_path)), picture)
    return picture


def load_questions(path):
    """Read and validate a question set. Raises QuestionFileError with advice.
    Pictures that are missing or not PNG/JPG are left out and noted in
    board.warnings rather than stopping the game."""
    fieldnames, raw = _read_rows(path)
    columns = _column_map(path, fieldnames)
    get = lambda row, key: (row.get(columns[key]) or "").strip() if key in columns else ""

    problems = []
    warnings = []
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

        r = whole_number(get(row, "Row"))
        c = whole_number(get(row, "Col"))
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
        picture = None
        if get(row, "Picture"):
            picture = _picture_path(path, get(row, "Picture"))
            if os.path.splitext(picture)[1].lower() not in PICTURE_TYPES:
                warnings.append("line %d: Row %d, Col %d picture is not a PNG or JPG file: %s"
                                % (line, r, c, picture))
                picture = None
            elif not os.path.isfile(picture):
                warnings.append("line %d: Row %d, Col %d picture not found: %s"
                                % (line, r, c, picture))
                picture = None
        questions[(r, c)] = {"question": question, "answer": answer, "picture": picture}

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

    return Board(categories, questions, n_rows, n_cols, path, warnings)


def score_change(points, correct, steal, mode):
    """Points won or lost for one answer. Nice mode has no penalty and pays
    half for a steal; savage mode pays and penalises the full value."""
    if correct:
        return points // 2 if steal and mode == "nice" else points
    return 0 if mode == "nice" else -points


# ------------------------------------------------------------------- game --
class Game(object):
    def __init__(self, boards, teams, time_limit=30, buzzer="buzzer2.wav",
                 ticktock="ticktock.wav", mode="nice"):
        if isinstance(boards, Board):
            boards = [boards]
        if mode not in MODES:
            raise ValueError("mode must be one of %s" % ", ".join(MODES))
        self.mode = mode
        self.boards = list(boards)
        self.round_index = 0
        self.teams = teams
        self.scores = [0] * len(teams)
        self.time_limit = time_limit
        self.buzzer = find_sound(buzzer)
        self.used = set()
        self.team_index = -1
        self.opener = -1                # the team that picked the current square
        self.stealers = set()           # teams chosen on the steal screen
        self.state = "board"            # board | question | answer | steal | round_over | game_over
        self.current = None
        self.started = 0.0
        self.buzzed = False
        self.paused = False
        self.pause_started = 0.0
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
        pygame.display.set_caption("Jeopardy (%s mode) - %s" % (self.mode, name))

    def round_finished(self):
        return len(self.used) >= self.board.n_rows * self.board.n_cols

    def end_round(self):
        """Leave the current round: on to the next one, or to the winner screen
        if this was the final round."""
        self.confirm_until = 0.0
        self.close_question()
        self.state = "round_over" if self.has_next_round else "game_over"

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
        self.close_question()
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

    def award_rect(self):
        return (self.w * 3 / 8.0, self.board_h - 110, self.w / 4.0, 80)

    @staticmethod
    def points(row):
        return row * POINTS_STEP

    # -- drawing -----------------------------------------------------------
    def draw_score_bar(self):
        pygame.draw.rect(self.screen, DARK, (0, self.board_h, self.w, self.score_h))
        width = self.teams_w / float(len(self.teams))
        for i, name in enumerate(self.teams):
            box = pygame.Rect(i * width + 4, self.board_h + 4, width - 8, self.score_h - 8)
            chosen = i == self.team_index or i in self.stealers
            out = self.state == "steal" and i == self.opener    # got it wrong, can't steal
            pygame.draw.rect(self.screen, BLUE if chosen else DARK, box)
            pygame.draw.rect(self.screen, GOLD if chosen else (RED if out else GREY), box, 3)
            draw_text(self.screen, name, (box.x, box.y + 6, box.w, box.h * 0.40),
                      GREY if out else WHITE, 30, 11, True)
            draw_text(self.screen, str(self.scores[i]),
                      (box.x, box.y + box.h * 0.42, box.w, box.h * 0.52),
                      GREY if out else GOLD, 46, 14, True)
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
        heading = "%s  -  %d points" % (name, self.points(row))
        if self.state == "steal":
            heading += "  -  STEALS"
        draw_text(self.screen, heading, (0, 20, self.w, 46), GOLD, 34, 14, True)
        picture = item.get("picture")
        if picture and draw_picture(self.screen, picture,
                                    (60, top * 0.10, self.w - 120, top * 0.53)):
            # the picture takes most of the space; question, timer and answer
            # squeeze in below it
            question_box = (60, top * 0.63, self.w - 120, top * 0.085)
            timer_box = (0, top * 0.72, self.w, top * 0.16)
            answer_box = (60, top * 0.715, self.w - 120, top * 0.075)
            question_size = answer_size = 40
        else:
            question_box = (60, top * 0.13, self.w - 120, top * 0.40)
            timer_box = (0, top * 0.62, self.w, top * 0.16)
            answer_box = (60, top * 0.55, self.w - 120, top * 0.26)
            question_size, answer_size = 54, 46
        draw_text(self.screen, item["question"], question_box, WHITE, question_size, 16, True)

        if self.state == "question":
            left = self.time_left()
            colour = WHITE if self.paused else (RED if left <= 5 else GOLD)
            text = "PAUSED" if self.paused else ("TIME UP" if left == 0 else "%0.0f" % left)
            draw_text(self.screen, text, timer_box, colour, 80, 24, True)
            hint = ("paused - press P to resume" if self.paused else
                    "click anywhere or press SPACE to reveal the answer  -  P to pause")
            draw_text(self.screen, hint, (0, top - 50, self.w, 40), WHITE, 24, 12)
            if left == 0 and not self.buzzed:
                self.buzz()
            self.draw_score_bar()
            return

        draw_text(self.screen, item["answer"], answer_box, GOLD, answer_size, 14, True)
        if self.state == "answer":
            right, wrong = self.button_rects()
            loss = self.award(False)
            pygame.draw.rect(self.screen, GREEN, right)
            pygame.draw.rect(self.screen, RED, wrong)
            draw_text(self.screen, "CORRECT  +%d" % self.award(True), right, WHITE, 30, 12, True)
            draw_text(self.screen, "WRONG  %d" % loss if loss else "WRONG", wrong,
                      WHITE, 30, 12, True)
        else:
            draw_text(self.screen, "click every team that got it right (+%d each), then AWARD"
                      % self.award(True, steal=True), (0, top * 0.79, self.w, 34), WHITE, 24, 12)
            button = self.award_rect()
            pygame.draw.rect(self.screen, GREEN if self.stealers else GREY, button)
            draw_text(self.screen, "AWARD STEALS" if self.stealers else "NO STEALS",
                      button, WHITE, 30, 12, True)
        self.draw_score_bar()

    # -- actions -----------------------------------------------------------
    def time_left(self):
        now = self.pause_started if self.paused else time.perf_counter()
        return max(0, self.time_limit - (now - self.started))

    def toggle_pause(self):
        """Pause or resume the countdown while a question is up."""
        if self.state != "question":
            return
        if self.paused:
            self.started += time.perf_counter() - self.pause_started
            self.paused = False
        else:
            self.pause_started = time.perf_counter()
            self.paused = True

    def update_ticktock(self):
        """Tick while a question is up and the clock is running, and at no
        other time. Called every frame, so every way of leaving a question
        (reveal, ESC, time up, ending the round) stops the sound."""
        if self.ticktock is None:
            return
        wanted = self.state == "question" and not self.paused and self.time_left() > 0
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
        self.opener = self.team_index
        self.stealers = set()
        self.state = "question"
        self.started = time.perf_counter()
        self.buzzed = False
        self.paused = False

    def close_question(self):
        self.state, self.current, self.team_index = "board", None, -1
        self.opener, self.stealers = -1, set()

    def reveal(self):
        if self.state == "question" and not self.paused:
            self.state = "answer"

    def award(self, correct, steal=False):
        """Points for a right or wrong answer, from the picking team or a stealer."""
        row, _ = self.current
        return score_change(self.points(row), correct, steal, self.mode)

    def select_team(self, team):
        """Click on a team: on the board it picks who chooses the next square;
        on the steal screen it adds or removes a stealer. The picking team is
        fixed while a question is up."""
        if self.state == "board":
            self.team_index = team
        elif self.state == "steal" and team != self.opener:
            self.stealers ^= {team}

    def score(self, correct):
        """Score the team that picked the square. Wrong opens the steal screen."""
        if self.state != "answer":
            return
        self.scores[self.team_index] += self.award(correct)
        if not correct and len(self.teams) > 1:
            self.state, self.team_index = "steal", -1
        else:
            self.close_question()

    def award_steals(self):
        """Give every chosen stealer the steal points, then back to the board."""
        if self.state != "steal":
            return
        for team in self.stealers:
            self.scores[team] += self.award(True, steal=True)
        self.close_question()

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
                self.close_question()
            elif event.key == pygame.K_r and self.state == "question":
                self.started, self.buzzed, self.paused = time.perf_counter(), False, False
            elif event.key == pygame.K_p and self.state == "question":
                self.toggle_pause()
            elif event.key == pygame.K_SPACE and self.state == "question":
                self.reveal()
            elif event.key == pygame.K_y:
                self.score(True)
            elif event.key == pygame.K_n:
                self.score(False)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.award_steals()
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
                self.select_team(team)
                return True
            if self.state == "board":
                cell = self.cell_at(event.pos)
                if cell:
                    self.open_cell(cell)
                return True
            if self.state == "question":
                self.reveal()
            elif self.state == "answer":
                right, wrong = self.button_rects()
                if pygame.Rect(right).collidepoint(event.pos):
                    self.score(True)
                elif pygame.Rect(wrong).collidepoint(event.pos):
                    self.score(False)
            elif self.state == "steal":
                if pygame.Rect(self.award_rect()).collidepoint(event.pos):
                    self.award_steals()
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
                        help="sound played at time up, if the file exists "
                             '(default buzzer2.wav; --buzzer "" for silent mode, no buzzer)')
    parser.add_argument("--ticktock", default="ticktock.wav", metavar="WAV",
                        help="sound looped while the timer runs, if the file exists "
                             '(default ticktock.wav; --ticktock "" for silence)')
    parser.add_argument("--mode", choices=MODES, default="nice",
                        help="nice (default): no penalty for a wrong answer, a steal earns "
                             "half the points; savage: a wrong answer loses the full value, "
                             "a steal earns the full points")
    parser.add_argument("--check", action="store_true",
                        help="check the CSV and print a summary without starting the game")
    args = parser.parse_args(argv)

    try:
        boards = load_rounds(parse_csv_list(args.csv_files))
        teams = parse_teams(args.teams) if args.teams else None
    except QuestionFileError as err:
        sys.stderr.write("\n%s\n\n" % err)
        return 2

    for number, board in enumerate(boards, 1):
        if board.warnings:
            prefix = "Round %d: " % number if len(boards) > 1 else ""
            sys.stderr.write("%sWarning - %s: these questions will be shown without a "
                             "picture:\n%s\n" % (prefix, os.path.basename(board.path),
                                                 "\n".join("  - " + w for w in board.warnings)))

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
         ticktock=args.ticktock, mode=args.mode).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
