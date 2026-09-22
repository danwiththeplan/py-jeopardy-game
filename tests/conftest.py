import pygame
import pytest

VALID_3X3 = """Row,Col,Question,Answer,Categories
1,0,The basic unit of life,The cell,Cells
2,0,The organelle that releases energy from glucose,Mitochondrion,Cells
3,0,The process by which a cell divides to make two identical cells,Mitosis,Cells
1,1,The molecule that carries genetic information,DNA,Genetics
2,1,An alternative form of a gene,Allele,Genetics
3,1,Having two different alleles for a gene,Heterozygous,Genetics
1,2,An organism that makes its own food,Producer,Ecology
2,2,All the populations living in one area,Community,Ecology
3,2,The role an organism plays in its ecosystem,Niche,Ecology
"""


@pytest.fixture(scope="session", autouse=True)
def _pygame_font():
    """draw_text/get_font need the font module initialised; no display required."""
    pygame.font.init()
    yield
    pygame.font.quit()


@pytest.fixture
def write_csv(tmp_path):
    """Factory fixture: write_csv("name.csv", "contents") -> path to the file."""
    def _write(name, contents):
        path = tmp_path / name
        path.write_text(contents, encoding="utf-8")
        return str(path)
    return _write


@pytest.fixture
def valid_csv(write_csv):
    return write_csv("valid.csv", VALID_3X3)
