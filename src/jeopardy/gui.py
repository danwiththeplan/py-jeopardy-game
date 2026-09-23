"""
Classroom Jeopardy with a setup window - no command line needed.

    jeopardy-gui

A setup window opens first. In it you:
    - add 1 to 10 question-set CSV files, one per round, and put them in order
    - choose how many teams are playing and type their names
    - pick the time per question (15, 30, 45 or 60 seconds, or no limit)
    - tick Savage mode (full penalties, full points for a steal) if wanted
    - tick Silent mode to turn off the ticking clock and the time-up buzzer

START GAME checks every file first and lists anything wrong with them, then
closes the setup window and starts the game.

This is the entry point used to build the Windows executable.
"""

import os
import sys

from jeopardy.core import MAX_TEAMS, Game, QuestionFileError, load_rounds

MAX_ROUNDS = 10
TIME_CHOICES = (("15 seconds", 15), ("30 seconds", 30), ("45 seconds", 45),
                ("60 seconds", 60), ("No limit", None))
DEFAULT_TIME = "30 seconds"
DEFAULT_TEAMS = 2


class Settings(object):
    """Everything chosen in the setup window."""

    def __init__(self):
        self.paths = []
        self.team_count = DEFAULT_TEAMS
        self.team_names = [""] * MAX_TEAMS
        self.time_label = DEFAULT_TIME
        self.savage = False
        self.silent = False
        self.folder = os.getcwd()


# ------------------------------------------------------------------ logic --
def time_limit(label):
    """Seconds for a time choice label, or None for no limit."""
    return dict(TIME_CHOICES)[label]


def team_list(names, count):
    """The first `count` names, with blanks filled in as Team 1, Team 2..."""
    if not 1 <= count <= MAX_TEAMS:
        raise QuestionFileError("Choose between 1 and %d teams." % MAX_TEAMS)
    return [(names[i] if i < len(names) else "").strip() or "Team %d" % (i + 1)
            for i in range(count)]


def add_paths(paths, new):
    """Append the new files, skipping repeats and stopping at MAX_ROUNDS.
    Returns the new list and how many files were left out for lack of room."""
    paths = list(paths)
    skipped = 0
    for path in new:
        if path in paths:
            continue
        if len(paths) >= MAX_ROUNDS:
            skipped += 1
            continue
        paths.append(path)
    return paths, skipped


def move(items, index, step):
    """Move items[index] up (step -1) or down (step +1). Returns the new list
    and the item's new index."""
    items = list(items)
    target = index + step
    if 0 <= index < len(items) and 0 <= target < len(items):
        items[index], items[target] = items[target], items[index]
        return items, target
    return items, index


def prepare(settings):
    """Check the settings and load every round. Returns the Game arguments,
    or raises QuestionFileError explaining what to fix."""
    if not settings.paths:
        raise QuestionFileError("Add at least one question-set CSV file.")
    if len(settings.paths) > MAX_ROUNDS:
        raise QuestionFileError("Use at most %d question-set files." % MAX_ROUNDS)
    teams = team_list(settings.team_names, settings.team_count)
    boards = load_rounds(settings.paths)
    buzzer, ticktock = ("", "") if settings.silent else ("buzzer2.wav", "ticktock.wav")
    return dict(boards=boards, teams=teams, time_limit=time_limit(settings.time_label),
                mode="savage" if settings.savage else "nice",
                buzzer=buzzer, ticktock=ticktock)


# ----------------------------------------------------------------- window --
class SetupWindow(object):
    """The tkinter setup screen. `run()` returns True to start a game with
    the settings, or False if the window was closed."""

    def __init__(self, settings):
        import tkinter as tk
        from tkinter import ttk

        self.tk, self.ttk = tk, ttk
        self.settings = settings
        self.start = False

        self.root = tk.Tk()
        self.root.title("Classroom Jeopardy - setup")
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self.root, padding=14)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.build_rounds(frame).grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        lower = ttk.Frame(frame)
        lower.grid(row=1, column=0, sticky="ew")
        lower.columnconfigure(0, weight=1)
        self.build_teams(lower).grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.build_options(lower).grid(row=0, column=1, sticky="nsew")

        start = ttk.Button(frame, text="START GAME", command=self.on_start)
        start.grid(row=2, column=0, sticky="e", pady=(12, 0), ipadx=20, ipady=6)
        self.root.bind("<Return>", lambda event: self.on_start())

        self.refresh_paths()
        self.refresh_teams()
        self.root.minsize(640, 520)

    # -- sections ----------------------------------------------------------
    def build_rounds(self, parent):
        tk, ttk = self.tk, self.ttk
        box = ttk.LabelFrame(parent, text="Rounds (1 to %d question-set CSV files, played "
                                           "top to bottom)" % MAX_ROUNDS, padding=8)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.path_list = tk.Listbox(box, height=MAX_ROUNDS, activestyle="none",
                                    exportselection=False)
        self.path_list.grid(row=0, column=0, sticky="nsew")
        buttons = ttk.Frame(box)
        buttons.grid(row=0, column=1, sticky="n", padx=(8, 0))
        for text, command in (("Add files...", self.on_add), ("Remove", self.on_remove),
                              ("Move up", lambda: self.on_move(-1)),
                              ("Move down", lambda: self.on_move(1)),
                              ("Clear all", self.on_clear)):
            ttk.Button(buttons, text=text, command=command).pack(fill="x", pady=2)
        self.count_label = ttk.Label(box)
        self.count_label.grid(row=1, column=0, sticky="w", pady=(4, 0))
        return box

    def build_teams(self, parent):
        tk, ttk = self.tk, self.ttk
        box = ttk.LabelFrame(parent, text="Teams", padding=8)
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text="Number of teams:").grid(row=0, column=0, sticky="w")
        self.team_count = tk.IntVar(value=self.settings.team_count)
        ttk.Spinbox(box, from_=1, to=MAX_TEAMS, width=4, state="readonly",
                    textvariable=self.team_count, command=self.refresh_teams
                    ).grid(row=0, column=1, sticky="w", pady=(0, 6))
        self.team_vars, self.team_rows = [], []
        for i in range(MAX_TEAMS):
            var = tk.StringVar(value=self.settings.team_names[i])
            label = ttk.Label(box, text="Team %d:" % (i + 1))
            entry = ttk.Entry(box, textvariable=var, width=28)
            self.team_vars.append(var)
            self.team_rows.append((label, entry))
        ttk.Label(box, text="Blank names become Team 1, Team 2...", foreground="grey"
                  ).grid(row=MAX_TEAMS + 1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        return box

    def build_options(self, parent):
        tk, ttk = self.tk, self.ttk
        box = ttk.LabelFrame(parent, text="Options", padding=8)
        ttk.Label(box, text="Time per question:").pack(anchor="w")
        self.time_choice = tk.StringVar(value=self.settings.time_label)
        ttk.Combobox(box, textvariable=self.time_choice, state="readonly", width=14,
                     values=[label for label, _ in TIME_CHOICES]).pack(anchor="w", pady=(2, 12))
        self.savage = tk.BooleanVar(value=self.settings.savage)
        ttk.Checkbutton(box, text="Savage mode", variable=self.savage).pack(anchor="w")
        ttk.Label(box, text="wrong answers lose points,\nsteals earn full points",
                  foreground="grey").pack(anchor="w", padx=(22, 0), pady=(0, 8))
        self.silent = tk.BooleanVar(value=self.settings.silent)
        ttk.Checkbutton(box, text="Silent mode", variable=self.silent).pack(anchor="w")
        ttk.Label(box, text="no ticking clock, no buzzer",
                  foreground="grey").pack(anchor="w", padx=(22, 0))
        return box

    # -- updates -----------------------------------------------------------
    def refresh_paths(self, select=None):
        self.path_list.delete(0, "end")
        for n, path in enumerate(self.settings.paths, 1):
            self.path_list.insert("end", "Round %d:  %s" % (n, os.path.basename(path)))
        if select is not None and self.settings.paths:
            self.path_list.selection_set(select)
            self.path_list.see(select)
        count = len(self.settings.paths)
        self.count_label.config(text="%d of %d rounds" % (count, MAX_ROUNDS) if count else
                                "No files yet - click Add files...")

    def refresh_teams(self):
        count = self.team_count.get()
        for i, (label, entry) in enumerate(self.team_rows):
            if i < count:
                label.grid(row=i + 1, column=0, sticky="w", pady=1)
                entry.grid(row=i + 1, column=1, sticky="ew", pady=1)
            else:
                label.grid_remove()
                entry.grid_remove()

    def selected(self):
        chosen = self.path_list.curselection()
        return chosen[0] if chosen else None

    # -- buttons -----------------------------------------------------------
    def on_add(self):
        from tkinter import filedialog, messagebox
        chosen = filedialog.askopenfilenames(
            parent=self.root, title="Choose question-set CSV files",
            initialdir=self.settings.folder,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not chosen:
            return
        self.settings.folder = os.path.dirname(chosen[0])
        self.settings.paths, skipped = add_paths(self.settings.paths, chosen)
        self.refresh_paths(len(self.settings.paths) - 1)
        if skipped:
            messagebox.showwarning(
                "Too many rounds", "A game can have at most %d rounds, so %d file%s "
                "left out." % (MAX_ROUNDS, skipped, " was" if skipped == 1 else "s were"),
                parent=self.root)

    def on_remove(self):
        index = self.selected()
        if index is None:
            return
        del self.settings.paths[index]
        self.refresh_paths(min(index, len(self.settings.paths) - 1))

    def on_move(self, step):
        index = self.selected()
        if index is None:
            return
        self.settings.paths, index = move(self.settings.paths, index, step)
        self.refresh_paths(index)

    def on_clear(self):
        self.settings.paths = []
        self.refresh_paths()

    def collect(self):
        self.settings.team_count = self.team_count.get()
        self.settings.team_names = [var.get() for var in self.team_vars]
        self.settings.time_label = self.time_choice.get()
        self.settings.savage = self.savage.get()
        self.settings.silent = self.silent.get()

    def on_start(self):
        self.collect()
        try:
            self.game_args = prepare(self.settings)
        except QuestionFileError as err:
            self.show_problems(str(err))
            return
        self.start = True
        self.root.destroy()

    def show_problems(self, text):
        """Problem reports can be long, so show them in a scrolling box."""
        tk, ttk = self.tk, self.ttk
        dialog = tk.Toplevel(self.root)
        dialog.title("Can't start the game")
        dialog.transient(self.root)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        lines = text.count("\n") + 1
        view = tk.Text(dialog, wrap="word", width=80, height=min(24, max(4, lines)),
                       padx=10, pady=10)
        view.insert("1.0", text)
        view.config(state="disabled")
        scroll = ttk.Scrollbar(dialog, command=view.yview)
        view.config(yscrollcommand=scroll.set)
        view.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        ttk.Button(dialog, text="OK", command=dialog.destroy).grid(
            row=1, column=0, columnspan=2, pady=8)
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.grab_set()

    def run(self):
        self.root.mainloop()
        return self.start


# ------------------------------------------------------------------- main --
def _sharp_on_windows():
    """Without this, Windows scales the setup window and the game up and
    they look blurry on high-DPI screens."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def main():
    try:
        import tkinter  # noqa: F401
    except ImportError:
        sys.stderr.write("\nThe setup window needs tkinter, which isn't installed.\n"
                         "On Debian/Ubuntu: sudo apt install python3-tk\n"
                         "Or use the command-line version: jeopardy myset.csv\n\n")
        return 1
    _sharp_on_windows()
    window = SetupWindow(Settings())
    if window.run():
        Game(**window.game_args).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
