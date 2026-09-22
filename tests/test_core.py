import pytest

from jeopardy.core import (
    QuestionFileError,
    load_questions,
    load_rounds,
    parse_csv_list,
    parse_teams,
)


# --------------------------------------------------------------- load_questions --
def test_valid_board_loads(valid_csv):
    board = load_questions(valid_csv)
    assert (board.n_rows, board.n_cols) == (3, 3)
    assert board.categories == ["Cells", "Genetics", "Ecology"]
    assert board.questions[(1, 0)] == {"question": "The basic unit of life", "answer": "The cell"}
    assert len(board.questions) == 9


def test_missing_file_raises():
    with pytest.raises(QuestionFileError, match="No such file"):
        load_questions("does-not-exist.csv")


def test_empty_file_raises(write_csv):
    path = write_csv("empty.csv", "")
    with pytest.raises(QuestionFileError, match="empty"):
        load_questions(path)


def test_missing_required_column_raises(write_csv):
    path = write_csv("no_answer.csv", "Row,Col,Question,Categories\n1,0,Q,Cat\n")
    with pytest.raises(QuestionFileError, match="missing the column"):
        load_questions(path)


def test_non_numeric_row_raises(write_csv):
    contents = "Row,Col,Question,Answer,Categories\nfirst,0,Q,A,Cat\n"
    with pytest.raises(QuestionFileError, match="Row must be a whole number"):
        load_questions(write_csv("bad_row.csv", contents))


def test_non_numeric_col_raises(write_csv):
    contents = "Row,Col,Question,Answer,Categories\n1,x,Q,A,Cat\n"
    with pytest.raises(QuestionFileError, match="Col must be a whole number"):
        load_questions(write_csv("bad_col.csv", contents))


def test_missing_question_raises(write_csv):
    contents = "Row,Col,Question,Answer,Categories\n1,0,,A,Cat\n"
    with pytest.raises(QuestionFileError, match="has no question"):
        load_questions(write_csv("no_question.csv", contents))


def test_missing_answer_raises(write_csv):
    contents = "Row,Col,Question,Answer,Categories\n1,0,Q,,Cat\n"
    with pytest.raises(QuestionFileError, match="has no answer"):
        load_questions(write_csv("no_answer_cell.csv", contents))


def test_duplicate_square_raises(write_csv):
    contents = (
        "Row,Col,Question,Answer,Categories\n"
        "1,0,Q1,A1,Cat\n"
        "1,0,Q2,A2,Cat\n"
    )
    with pytest.raises(QuestionFileError, match="already used"):
        load_questions(write_csv("dup.csv", contents))


def test_board_below_minimum_size_raises(write_csv):
    # a 2x2 board is smaller than MIN_SIDE (3)
    contents = (
        "Row,Col,Question,Answer,Categories\n"
        "1,0,Q,A,Cat1\n"
        "2,0,Q,A,\n"
        "1,1,Q,A,Cat2\n"
        "2,1,Q,A,\n"
    )
    with pytest.raises(QuestionFileError, match=r"2 x 2 board"):
        load_questions(write_csv("too_small.csv", contents))


def test_category_count_mismatch_raises(write_csv, valid_csv):
    text = open(valid_csv).read().replace("Ecology", "Biology", 1)  # only one line renamed
    with pytest.raises(QuestionFileError, match="category name"):
        load_questions(write_csv("mismatch.csv", text))


def test_repeated_category_per_line_is_allowed(write_csv):
    contents = (
        "Row,Col,Question,Answer,Categories\n"
        "1,0,Q,A,Cats\n"
        "2,0,Q,A,Cats\n"
        "3,0,Q,A,Cats\n"
        "1,1,Q,A,Dogs\n"
        "2,1,Q,A,Dogs\n"
        "3,1,Q,A,Dogs\n"
        "1,2,Q,A,Birds\n"
        "2,2,Q,A,Birds\n"
        "3,2,Q,A,Birds\n"
    )
    board = load_questions(write_csv("repeated_cats.csv", contents))
    assert board.categories == ["Cats", "Dogs", "Birds"]


def test_incomplete_board_reports_missing_squares(write_csv):
    contents = (
        "Row,Col,Question,Answer,Categories\n"
        "1,0,Q,A,Cat1\n"
        "2,0,Q,A,\n"
        "3,0,Q,A,\n"
        "1,1,Q,A,Cat2\n"
        "2,1,Q,A,\n"
        "3,1,Q,A,\n"
        "1,2,Q,A,Cat3\n"
        "2,2,Q,A,\n"
        # Row 3, Col 2 is missing
    )
    with pytest.raises(QuestionFileError, match="Row 3, Col 2"):
        load_questions(write_csv("incomplete.csv", contents))


# ------------------------------------------------------------------ load_rounds --
def test_load_rounds_returns_a_board_per_file(valid_csv):
    boards = load_rounds([valid_csv, valid_csv])
    assert len(boards) == 2


def test_load_rounds_collects_errors_from_all_files(valid_csv, write_csv):
    bad = write_csv("bad.csv", "")
    with pytest.raises(QuestionFileError, match=r"Round 2: .*empty"):
        load_rounds([valid_csv, bad])


# ------------------------------------------------------------------- parse_teams --
def test_parse_teams_splits_and_trims():
    assert parse_teams(" Kea , Weta ,Tuatara") == ["Kea", "Weta", "Tuatara"]


def test_parse_teams_rejects_empty():
    with pytest.raises(QuestionFileError):
        parse_teams("")


def test_parse_teams_rejects_too_many():
    with pytest.raises(QuestionFileError):
        parse_teams(",".join("Team%d" % i for i in range(9)))


# --------------------------------------------------------------- parse_csv_list --
def test_parse_csv_list_splits_and_trims():
    assert parse_csv_list(" a.csv, b.csv ,c.csv") == ["a.csv", "b.csv", "c.csv"]


def test_parse_csv_list_rejects_empty():
    with pytest.raises(QuestionFileError):
        parse_csv_list("")
