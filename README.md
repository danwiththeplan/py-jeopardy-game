# Jeopardy in Python

A classroom Jeopardy game built with [pygame](https://www.pygame.org/). Jeopardy games made from PowerPoint slides are quick to build, but they don't keep track of which questions have been played or what each team has scored. This game does both, so you can concentrate on running the activity.

Questions are stored in a plain CSV file that you can edit in any spreadsheet program, so a new question set for any subject takes minutes to make. It works well for revision, for introducing new material, or as an end-of-unit activity.

## Features

- Boards of any size from 3×3 up to 8×8, read automatically from the CSV
- Up to 8 teams, with scores shown along the bottom of the screen
- A countdown timer for each question, with an optional ticking clock and time-up buzzer, and a pause/resume control
- A silent mode (`--buzzer ""`) for classrooms where the buzzer sound isn't wanted
- Multiple rounds from separate CSV files, with scores carried over between rounds
- Steals: when a team gets a question wrong, every other team that got it right can be given steal points at once
- Two scoring modes: `--mode nice` (the default, no penalties and half points for a steal) and `--mode savage` (full penalties and full points for a steal)
- A winner screen with a full ranking (ties are handled)
- A `--check` mode that validates a question file and explains exactly what is wrong with it
- Resizable window and fullscreen mode for projectors

## Requirements

- Python 3.12 or newer
- [Poetry](https://python-poetry.org/docs/#installation) for installing dependencies (pygame is the only one)

If you don't have Poetry yet, the simplest way to install it is:

```shell
pipx install poetry
```

## Installation

Clone the repository and install the dependencies:

```shell
git clone https://github.com/danwiththeplan/py-jeopardy-game.git
cd py-jeopardy-game
poetry install
```

Poetry creates a virtual environment for the project and installs pygame into it. You only need to do this once.

## Development

The `jeopardy` package lives under `src/`. Run the test suite with:

```shell
poetry run pytest
```

## Running the game

Put `poetry run` in front of each command so the game uses the project's environment:

```shell
poetry run jeopardy myset.csv
```

(`poetry run python -m jeopardy myset.csv` works the same way, if you'd rather invoke the package directly.)

A ready-made example set is included at `data/example.csv`:

```shell
poetry run jeopardy data/example.csv
```

You'll be asked how many teams are playing and what they're called, and then the board opens. To skip the prompts, give the team names on the command line:

```shell
poetry run jeopardy myset.csv --teams "Kea,Weta,Tuatara"
```

### Command-line options

| Option | What it does |
| --- | --- |
| `--teams "A,B,C"` | Team names, separated by commas (1 to 8 teams). If omitted, you are prompted. |
| `--time SECONDS` | Seconds allowed per question (default 30, minimum 5). |
| `--buzzer FILE.wav` | Sound played when time runs out (default `buzzer2.wav`). Use `--buzzer ""` for silent mode (no buzzer). |
| `--ticktock FILE.wav` | Sound looped while the timer runs (default `ticktock.wav`). Use `--ticktock ""` for silence. |
| `--mode nice` / `--mode savage` | Scoring mode (default `nice`). See [Scoring](#scoring). |
| `--check` | Check the CSV file(s) and print a summary without starting the game. |

Examples:

```shell
poetry run jeopardy myset.csv --check
poetry run jeopardy myset.csv --teams "Kea,Weta" --time 45
poetry run jeopardy myset.csv --mode savage
poetry run jeopardy myset.csv --ticktock ""
poetry run jeopardy myset.csv --buzzer ""
```

Run `poetry run jeopardy --help` to see all options.

### Playing several rounds

Give a comma-separated list of CSV files (no spaces, or put quotes around the whole list). The rounds are played in the order listed, each board can be a different size, and scores carry over from round to round.

```shell
poetry run jeopardy round1.csv,round2.csv,final.csv
```

When every square in a round has been played, a "Round complete" screen appears. Click or press ENTER to start the next round.

## Creating a question set

Each question set is a CSV file with these five columns (extra columns are ignored, and column names are not case-sensitive):

| Column | Meaning |
| --- | --- |
| `Row` | The point value row, starting at 1. Row 1 is worth 100 points, Row 2 is 200, and so on. |
| `Col` | The category column, starting at 0. |
| `Question` | The clue shown on screen. |
| `Answer` | The answer revealed afterwards. |
| `Categories` | Category names, one per line, down the first few lines of the file. The first name is column 0, the second is column 1, and so on. |

The board size comes from the file itself: the number of columns is the highest `Col` plus one, and the number of rows is the highest `Row`. Every square on the board must have a question.

Here is a complete 3×3 example:

```csv
Row,Col,Question,Answer,Categories
1,0,The basic unit of life,The cell,Cells
2,0,The organelle that releases energy from glucose,Mitochondrion,Cells
3,0,The process by which a cell divides to make two identical cells,Mitosis,Cells
1,1,The molecule that carries genetic information,DNA,Genetics
2,1,An alternative form of a gene,Allele,Genetics
3,1,Having two different alleles for a gene,Heterozygous,Genetics
1,2,An organism that makes its own food,Producer,Ecology
2,2,All the populations living in one area,Community,Ecology
3,2,The role an organism plays in its ecosystem,Niche,Ecology
```

A few tips:

- Build the file in Excel, Google Sheets or LibreOffice and save it as **CSV UTF-8**. An `.xlsx` file won't load.
- It's fine to repeat the category name on every line of its column instead of listing each one once.
- Always run `--check` on a new file first. If anything is wrong, such as a missing answer, a duplicated square or a gap in the board, it lists every problem with its line number.

## Controls

| Action | How |
| --- | --- |
| Choose the answering team | Click the team at the bottom of the screen |
| Open a question | Click a value on the board (a team must be selected first) |
| Reveal the answer | Click the question, or press SPACE |
| Score the answer | Click CORRECT or WRONG, or press Y or N |
| Award steals | On the steal screen, click each team that got it right (click again to unselect), then click AWARD STEALS or press ENTER |
| Pause / resume the timer | P |
| Restart the timer | R |
| Back to the board | ESC |
| End the round early | Click END ROUND twice, or press PAGE DOWN |
| End the game | Click FINISH GAME twice (shown in the final round), or press PAGE DOWN |
| Toggle fullscreen | F |
| Quit | Q |

The winner screen appears automatically once the last square of the final round has been played, and the final scores are also printed in the terminal when you quit.

## Scoring

The team that picks a square answers it. While the timer runs, the other teams can work out (and write down) their own answers. Once the picking team has answered, reveal the answer and mark them CORRECT or WRONG. The picking team can't be changed while the question is up.

If they were WRONG, a steal screen appears. The picking team is shown greyed out with a red border. Click every other team that got it right; they light up, and clicking again unselects. Then click **AWARD STEALS** (or press ENTER) to give all of them the steal points at once. With no teams selected, the button reads **NO STEALS** and just goes back to the board. ESC also leaves without awarding anything.

| | `--mode nice` (default) | `--mode savage` |
| --- | --- | --- |
| Picking team right | + full value | + full value |
| Picking team wrong | no penalty | − full value |
| Each team awarded a steal | + half the value | + full value |

The current mode is shown in the window title, and the buttons always show exactly what will be gained or lost.

## Sounds

`ticktock.wav` loops while a question's timer is running and stops when the answer is revealed, time runs out, you pause the timer, or you leave the question. `buzzer2.wav` plays when time is up. Both are included in the package's `src/jeopardy/resources/` folder. The game looks for sound files in the current folder first and then in that resources folder, and it runs silently if a file is missing — so `--buzzer ""` or `--ticktock ""` also gives you silence on demand. Use `--buzzer` or `--ticktock` with a path to your own `.wav` file to override either sound.

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE) or later.

## Credits

Forked from [pharzan/py-jeopardy-game](https://github.com/pharzan/py-jeopardy-game).
