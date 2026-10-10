from pathlib import Path

import pytest
from pypdf import PdfWriter

from ai_governance.clauses import document_prefix, parse_documents

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "vendors"


def test_txt_splits_on_numbered_sections_with_document_prefix():
    doc_set = parse_documents([SAMPLES / "quillmark" / "terms.txt"])
    ids = [c.id for c in doc_set.clauses]
    assert ids[0] == "terms:preamble"
    assert "terms:sec-5" in ids
    assert doc_set.clause("terms:sec-5").heading == "Data Retention"


def test_docx_keeps_subsections_as_their_own_clauses():
    doc_set = parse_documents([SAMPLES / "brightloom" / "terms.docx"])
    assert "train and refine" in doc_set.clause("terms:sec-4.3").text


def test_several_documents_keep_their_own_prefixes():
    doc_set = parse_documents([SAMPLES / "quillmark" / "terms.txt", SAMPLES / "quillmark" / "dpa.txt"])
    assert set(doc_set.documents) == {"terms.txt", "dpa.txt"}
    assert doc_set.clause("dpa:sec-1").document == "dpa.txt"
    assert doc_set.clause("terms:sec-1").document == "terms.txt"


def test_prefix_collision_is_refused(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    for folder in ("a", "b"):
        (tmp_path / folder / "terms.txt").write_text("1. One. Text.", encoding="utf-8")
    with pytest.raises(ValueError, match="share the clause prefix"):
        parse_documents([tmp_path / "a" / "terms.txt", tmp_path / "b" / "terms.txt"])


def test_prefix_is_filename_safe():
    assert document_prefix(Path("Brightloom DPA v2.docx")) == "brightloom-dpa-v2"


def test_pdf_without_text_fails_clearly(tmp_path):
    # Text extraction from real PDFs is not unit-tested here (no PDF fixture
    # with a text layer); this covers the scanned-PDF failure path.
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    pdf = tmp_path / "scanned.pdf"
    with open(pdf, "wb") as f:
        writer.write(f)
    with pytest.raises(ValueError, match="no extractable text"):
        parse_documents([pdf])


def test_unsupported_type_is_refused(tmp_path):
    path = tmp_path / "terms.rtf"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        parse_documents([path])
