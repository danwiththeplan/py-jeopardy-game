import pytest

from jeopardy.core import Game, load_questions, main, score_change


# ----------------------------------------------------------------- score_change --
@pytest.mark.parametrize("correct, steal, mode, expected", [
    (True, False, "nice", 200),
    (True, True, "nice", 100),       # a steal earns half in nice mode
    (False, False, "nice", 0),       # no penalties in nice mode
    (False, True, "nice", 0),
    (True, False, "savage", 200),
    (True, True, "savage", 200),     # a steal earns the full points in savage mode
    (False, False, "savage", -200),
    (False, True, "savage", -200),   # stealers pay the full penalty too
])
def test_score_change(correct, steal, mode, expected):
    assert score_change(200, correct, steal, mode) == expected


def test_nice_steal_of_odd_value_rounds_down():
    assert score_change(150, True, True, "nice") == 75
    assert score_change(1, True, True, "nice") == 0


# ------------------------------------------------------------------------ --mode --
def test_mode_rejects_unknown_value(valid_csv, capsys):
    with pytest.raises(SystemExit):
        main([valid_csv, "--mode", "mean"])
    assert "invalid choice" in capsys.readouterr().err


# ------------------------------------------------------------------- game flow --
@pytest.fixture
def make_game(valid_csv, monkeypatch):
    """Build a real Game on SDL's dummy video/audio drivers (no window)."""
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")

    def _make(mode="nice", teams=("Kea", "Weta", "Tuatara")):
        return Game(load_questions(valid_csv), list(teams), buzzer="", ticktock="",
                    mode=mode)
    return _make


def open_square(game, team, cell=(2, 0)):          # row 2 = 200 points
    game.select_team(team)
    game.open_cell(cell)


def wrong(game):
    """Reveal the answer and mark the picking team wrong -> steal screen."""
    game.reveal()
    game.score(False)


def test_game_rejects_unknown_mode(make_game):
    with pytest.raises(ValueError):
        make_game(mode="mean")


def test_picking_team_correct_gets_full_points(make_game):
    game = make_game()
    open_square(game, 0)
    game.reveal()
    game.score(True)
    assert game.scores == [200, 0, 0]
    assert game.state == "board"


def test_cannot_score_before_the_answer_is_shown(make_game):
    game = make_game()
    open_square(game, 0)
    game.score(True)
    assert game.scores == [0, 0, 0] and game.state == "question"


def test_nice_several_teams_steal_at_once(make_game):
    game = make_game("nice")
    open_square(game, 0)
    wrong(game)
    assert game.state == "steal" and game.scores == [0, 0, 0]
    game.select_team(1)
    game.select_team(2)
    game.award_steals()
    assert game.scores == [0, 100, 100]
    assert game.state == "board"


def test_savage_several_teams_steal_at_once(make_game):
    game = make_game("savage")
    open_square(game, 0)
    wrong(game)
    game.select_team(1)
    game.select_team(2)
    game.award_steals()
    assert game.scores == [-200, 200, 200]


def test_clicking_a_stealer_again_unselects_it(make_game):
    game = make_game()
    open_square(game, 0)
    wrong(game)
    game.select_team(1)
    game.select_team(2)
    game.select_team(1)
    game.award_steals()
    assert game.scores == [0, 0, 100]


def test_picking_team_cannot_steal(make_game):
    game = make_game()
    open_square(game, 0)
    wrong(game)
    game.select_team(0)
    assert game.stealers == set()


def test_no_steals_chosen_goes_back_to_board(make_game):
    game = make_game("savage")
    open_square(game, 0)
    wrong(game)
    game.award_steals()
    assert game.state == "board" and game.scores == [-200, 0, 0]


def test_picking_team_is_fixed_during_a_question(make_game):
    game = make_game()
    open_square(game, 0)
    game.select_team(1)
    game.reveal()
    game.select_team(2)
    game.score(True)
    assert game.scores == [200, 0, 0]


def test_no_steal_screen_after_a_correct_answer(make_game):
    game = make_game()
    open_square(game, 0)
    game.reveal()
    game.score(True)
    assert game.state == "board"


def test_no_steal_screen_with_one_team(make_game):
    game = make_game(teams=("Kea",))
    open_square(game, 0)
    wrong(game)
    assert game.state == "board"


def test_stealers_reset_on_next_question(make_game):
    game = make_game()
    open_square(game, 0)
    wrong(game)
    game.select_team(1)
    game.award_steals()
    open_square(game, 2, cell=(1, 0))
    assert game.stealers == set() and game.opener == 2
