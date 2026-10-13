"""``scripts/check_public_repo.py``: no customer data in a tracked file (sales ticket 26).

Each case builds a throwaway git repository with the real `.gitignore`, writes a
deny-list OUTSIDE it, and runs the script there the way CI and the pre-commit
hook do. Every name and address below is invented.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from openpyxl import Workbook
from reportlab.pdfgen.canvas import Canvas

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "check_public_repo.py"
VAR = "DW_PUBLIC_REPO_DENYLIST"
NAME = "Đoàn Thị Hồng Nhung"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q")
    shutil.copy(REPO_ROOT / ".gitignore", path / ".gitignore")
    (path / "README.md").write_text("A public repository.\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "init")
    return path


def deny(tmp_path: Path, *terms: str) -> Path:
    path = tmp_path / "deny.txt"
    path.write_text("# invented terms\n" + "".join(f"{t}\n" for t in terms), encoding="utf-8")
    return path


def run(
    repo: Path, denylist: Path | None, *args: str, ci: bool = False
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("CI", VAR)}
    if denylist is not None:
        env[VAR] = str(denylist)
    if ci:
        env["CI"] = "true"
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def track(repo: Path, name: str, content: bytes | str) -> None:
    file = repo / name
    file.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        file.write_text(content, encoding="utf-8")
    else:
        file.write_bytes(content)
    _git(repo, "add", "-f", name)


@pytest.mark.parametrize(
    ("term", "text"),
    [
        (NAME, "DOAN THI HONG NHUNG"),
        ("doan thi hong nhung", NAME),
        ("Đoàn Thị   Hồng Nhung", "Đoàn Thị\nHồng Nhung"),
        ("nhung.doan@khach-hang.example", "Liên hệ: Nhung.Doan@khach-hang.example"),
    ],
    ids=["diacritics-in-term", "diacritics-in-file", "whitespace-and-line-break", "email"],
)
def test_a_term_in_a_tracked_file_fails_and_the_output_never_names_it(
    repo: Path, tmp_path: Path, term: str, text: str
) -> None:
    track(repo, "notes/order.md", f"# Order\n\n{text}\n")

    result = run(repo, deny(tmp_path, "an absent term", term))

    assert result.returncode == 1, result.stdout
    assert "notes/order.md:3: deny-list line 3" in result.stdout
    assert "nhung" not in (result.stdout + result.stderr).lower()


def test_a_clean_tree_passes(repo: Path, tmp_path: Path) -> None:
    track(repo, "notes/order.md", "Khách hàng giả lập, không có tên thật.\n")

    result = run(repo, deny(tmp_path, NAME))

    assert result.returncode == 0, result.stdout
    assert "0 deny-list hit(s) in tracked files, 1 term(s) checked." in result.stdout


def _xlsx(text: str) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet["B4"] = f"Người liên hệ: {text}"
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _pdf(text: str) -> bytes:
    out = io.BytesIO()
    canvas = Canvas(out)
    canvas.drawString(72, 720, f"Contact: {text}")
    canvas.save()
    return out.getvalue()


def _docx_runs(text: str) -> bytes:
    """How Word stores a name it was asked to format: split across runs, with
    character references. Read as raw XML, neither half is the name."""
    first, _, rest = text.partition(" Hong")
    body = (
        f"<w:p><w:r><w:t>{first} </w:t></w:r><w:r><w:rPr><w:b/></w:rPr>"
        f"<w:t>H&#7891;ng{rest}</w:t></w:r></w:p>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", body)
    return out.getvalue()


@pytest.mark.parametrize(
    ("name", "writer", "where"),
    [
        ("po.xlsx", _xlsx, "po.xlsx[xl/worksheets/sheet1.xml]"),
        ("po.pdf", _pdf, "po.pdf[page 1]"),
        ("survey.docx", _docx_runs, "survey.docx[word/document.xml]"),
    ],
)
def test_a_compressed_attachment_is_read_not_skipped(
    repo: Path, tmp_path: Path, name: str, writer: Callable[[str], bytes], where: str
) -> None:
    """Byte-scanning a spreadsheet or a PDF sees nothing: both are compressed."""
    # The PDF's standard font has no Vietnamese glyphs; the plain spelling is
    # still the same name once both sides are normalised.
    track(repo, f"attachments/{name}", writer("Doan Thi Hong Nhung"))

    result = run(repo, deny(tmp_path, NAME))

    assert result.returncode == 1, result.stdout
    assert f"attachments/{where}:" in result.stdout


def _embedded(text: str) -> bytes:
    """A workbook embedded in a Word document: a zip inside a zip."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "<w:p><w:r><w:t>See the table.</w:t></w:r></w:p>")
        archive.writestr("word/embeddings/Microsoft_Excel_Worksheet.xlsx", _xlsx(text))
    return out.getvalue()


@pytest.mark.parametrize(
    ("name", "content", "where"),
    [
        (
            "report.docx",
            _embedded("Doan Thi Hong Nhung"),
            "report.docx[word/embeddings/Microsoft_Excel_Worksheet.xlsx]"
            "[xl/worksheets/sheet1.xml]:1:",
        ),
        (
            "fixture.json",
            json.dumps({"pic": NAME}, ensure_ascii=True),
            "fixture.json:1:",
        ),
        ("page.html", "<p>&#272;o&#224;n Th&#7883; H&#7891;ng Nhung</p>", "page.html:1:"),
        ("export.csv", ("\ufeffma,ten\n1," + NAME + "\n").encode("utf-16-le"), "export.csv:2:"),
        (
            "PO_Doan_Thi_Hong_Nhung.md",
            "Nothing inside.\n",
            "PO_Doan_Thi_Hong_Nhung.md (its name):1:",
        ),
    ],
    ids=["embedded-workbook", "json-u-escapes", "character-references", "utf16-bom", "file-name"],
)
def test_an_encoded_or_hidden_term_is_still_found(
    repo: Path, tmp_path: Path, name: str, content: bytes | str, where: str
) -> None:
    """Each shape writes the name in a form a plain substring search does not see."""
    track(repo, f"data/{name}", content)

    result = run(repo, deny(tmp_path, NAME))

    assert result.returncode == 1, result.stdout
    assert f"data/{where} deny-list line 2" in result.stdout


def test_a_legacy_binary_office_file_is_a_finding(repo: Path, tmp_path: Path) -> None:
    """An .xls/.doc is an OLE compound file this script does not parse: not checked, not clean."""
    track(repo, "attachments/old.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 64)

    result = run(repo, deny(tmp_path, NAME))

    assert result.returncode == 1
    assert "attachments/old.xls: cannot be read (a legacy binary Office file)" in result.stdout


def test_a_scanned_pdf_is_reported_as_not_checked(repo: Path, tmp_path: Path) -> None:
    """The mock M16 is a scan on purpose; the scan says it did not see inside, and passes."""
    out = io.BytesIO()
    canvas = Canvas(out)
    canvas.rect(72, 72, 200, 100, fill=1)
    canvas.save()
    track(repo, "attachments/scan.pdf", out.getvalue())

    result = run(repo, deny(tmp_path, NAME))

    assert result.returncode == 0, result.stdout
    assert "attachments/scan.pdf: NOT CHECKED (a PDF with no text layer" in result.stdout


def test_a_file_that_cannot_be_read_is_a_finding(repo: Path, tmp_path: Path) -> None:
    track(repo, "attachments/broken.pdf", b"%PDF-1.7 not really a pdf")

    result = run(repo, deny(tmp_path, NAME))

    assert result.returncode == 1
    assert "attachments/broken.pdf: cannot be read" in result.stdout


def test_staged_mode_checks_the_index_not_the_working_tree(repo: Path, tmp_path: Path) -> None:
    """The commit holds the index's copy; the working tree can say anything else."""
    denylist = deny(tmp_path, NAME)
    order = repo / "notes/order.md"

    track(repo, "notes/order.md", f"{NAME}\n")
    order.write_text("cleaned, but not staged\n", encoding="utf-8")
    staged = run(repo, denylist, "--staged")
    assert staged.returncode == 1
    assert "notes/order.md:1: deny-list line 2" in staged.stdout
    assert "in staged files" in staged.stdout

    track(repo, "notes/order.md", "clean\n")
    order.write_text(f"{NAME}\n", encoding="utf-8")
    assert run(repo, denylist, "--staged").returncode == 0, "unstaged is not committed"


def test_a_deliberate_public_name_is_not_searched_for(repo: Path, tmp_path: Path) -> None:
    track(repo, "notes/process.md", "Proterial Vietnam, PRV, procedure WIV-03-012.\n")

    result = run(repo, deny(tmp_path, "Proterial", "PRV", "wiv-03-012", NAME))

    assert result.returncode == 0, result.stdout
    for line in (2, 3, 4):
        assert f"deny-list line {line} is a deliberate public name" in result.stdout
    assert "1 term(s) checked" in result.stdout


def test_no_deny_list_on_a_developer_machine_skips_loudly(repo: Path) -> None:
    result = run(repo, None)

    assert result.returncode == 0
    assert "PUBLIC-REPO GUARD SKIPPED" in result.stderr


def test_no_deny_list_in_ci_fails(repo: Path) -> None:
    result = run(repo, None, ci=True)

    assert result.returncode == 1
    assert "no deny-list in CI" in result.stdout


@pytest.mark.parametrize(
    ("make", "says"),
    [
        (lambda tmp, repo: tmp / "missing.txt", "cannot be read"),
        (lambda tmp, repo: deny(tmp), "holds no terms"),
        (lambda tmp, repo: deny(tmp, "Proterial"), "holds no terms"),
        (lambda tmp, repo: shutil.copy(deny(tmp, NAME), repo / "deny.txt"), "outside the checkout"),
    ],
    ids=["missing", "empty", "only-public-names", "inside-the-checkout"],
)
def test_a_deny_list_that_cannot_do_its_job_fails(
    repo: Path, tmp_path: Path, make: Callable[[Path, Path], Path], says: str
) -> None:
    result = run(repo, Path(make(tmp_path, repo)))

    assert result.returncode == 1
    assert says in result.stdout


def test_gitignore_must_cover_where_proterial_documents_land(repo: Path) -> None:
    """Checked with or without a deny-list: it needs none."""
    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

    result = run(repo, None)

    assert result.returncode == 1
    for probe in ("docs/design/handoff.pdf", "docs/requirements.docx", "docs/sales/survey.docx"):
        assert f".gitignore does not cover {probe}" in result.stdout


def test_a_tracked_document_under_docs_fails(repo: Path) -> None:
    track(repo, "docs/sales/requirements.docx", b"PK\x03\x04")
    track(repo, "docs/design/handoff.png", b"\x89PNG")

    result = run(repo, None)

    assert result.returncode == 1
    assert "docs/sales/requirements.docx is tracked" in result.stdout
    assert "docs/design/handoff.png is tracked" in result.stdout
