import pygame
import pytest

from jeopardy.core import MAX_TEAMS, Game, QuestionFileError, load_questions
from jeopardy.gui import (MAX_ROUNDS, TIME_CHOICES, Settings, add_paths, move, prepare,
                          team_list, time_limit)


# ------------------------------------------------------------------ choices --
def test_time_choices_match_the_dropdown():
    assert [time_limit(label) for label, _ in TIME_CHOICES] == [15, 30, 45, 60, None]


def test_blank_team_names_get_numbered():
    assert team_list(["Kea", "  ", "Weta", "unused"], 3) == ["Kea", "Team 2", "Weta"]


def test_team_names_are_trimmed_and_short_lists_padded():
    assert team_list([" Kea "], 2) == ["Kea", "Team 2"]


@pytest.mark.parametrize("count", [0, MAX_TEAMS + 1])
def test_team_count_out_of_range(count):
    with pytest.raises(QuestionFileError):
        team_list([], count)


# -------------------------------------------------------------- round files --
def test_add_paths_skips_repeats():
    assert add_paths(["a.csv"], ["b.csv", "a.csv", "b.csv"]) == (["a.csv", "b.csv"], 0)


def test_add_paths_stops_at_the_round_limit():
    existing = ["%d.csv" % i for i in range(MAX_ROUNDS - 1)]
    paths, skipped = add_paths(existing, ["x.csv", "y.csv", "z.csv"])
    assert len(paths) == MAX_ROUNDS
    assert paths[-1] == "x.csv"
    assert skipped == 2


def test_move_up_and_down():
    assert move(["a", "b", "c"], 2, -1) == (["a", "c", "b"], 1)
    assert move(["a", "b", "c"], 0, 1) == (["b", "a", "c"], 1)


def test_move_past_either_end_does_nothing():
    assert move(["a", "b"], 0, -1) == (["a", "b"], 0)
    assert move(["a", "b"], 1, 1) == (["a", "b"], 1)


# ------------------------------------------------------------------ prepare --
def make_settings(paths, **changes):
    settings = Settings()
    settings.paths = list(paths)
    for name, value in changes.items():
        setattr(settings, name, value)
    return settings


def test_prepare_defaults(valid_csv):
    args = prepare(make_settings([valid_csv]))
    assert len(args["boards"]) == 1
    assert args["teams"] == ["Team 1", "Team 2"]
    assert args["time_limit"] == 30
    assert args["mode"] == "nice"
    assert (args["buzzer"], args["ticktock"]) == ("buzzer2.wav", "ticktock.wav")


def test_prepare_savage_silent_no_limit(valid_csv):
    args = prepare(make_settings([valid_csv, valid_csv], savage=True, silent=True,
                                 time_label="No limit", team_count=3,
                                 team_names=["Kea", "Weta", "Tuatara"] + [""] * 5))
    assert len(args["boards"]) == 2
    assert args["teams"] == ["Kea", "Weta", "Tuatara"]
    assert args["time_limit"] is None
    assert args["mode"] == "savage"
    assert (args["buzzer"], args["ticktock"]) == ("", "")


def test_prepare_needs_a_file():
    with pytest.raises(QuestionFileError, match="at least one"):
        prepare(make_settings([]))


def test_prepare_rejects_too_many_files(valid_csv):
    with pytest.raises(QuestionFileError, match="at most"):
        prepare(make_settings([valid_csv] * (MAX_ROUNDS + 1)))


def test_prepare_reports_bad_files(valid_csv, write_csv):
    bad = write_csv("bad.csv", "Row,Col,Question\n1,0,Hi\n")
    with pytest.raises(QuestionFileError, match="Round 2"):
        prepare(make_settings([valid_csv, bad]))


# ------------------------------------------------------------ no time limit --
@pytest.fixture
def untimed_game(valid_csv, monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    game = Game(load_questions(valid_csv), ["Kea", "Weta"], time_limit=None,
                buzzer="", ticktock="")
    game.select_team(0)
    game.open_cell((1, 0))
    return game


def test_untimed_question_never_runs_out(untimed_game):
    untimed_game.started -= 10_000
    assert untimed_game.time_left() == float("inf")
    untimed_game.draw_question()
    assert not untimed_game.buzzed


def test_untimed_question_cannot_be_paused(untimed_game):
    untimed_game.toggle_pause()
    assert not untimed_game.paused
    untimed_game.reveal()
    assert untimed_game.state == "answer"


def test_a_second_game_can_draw_after_the_first_quits(valid_csv, monkeypatch):
    """The setup window starts one game after another in the same process."""
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    monkeypatch.setattr(pygame.event, "get", lambda: [pygame.event.Event(pygame.QUIT)])
    try:
        for _ in range(2):
            Game(load_questions(valid_csv), ["Kea"], buzzer="", ticktock="").run()
    finally:
        pygame.font.init()          # run() quit pygame; later tests still need fonts
