from mayan_drive_migration.filename_parser import parse_filename


def test_parse_expected_filename() -> None:
    metadata = parse_filename("isdr_wa_en_1f_v1- Base Doc - Identify Spurious Medicines.docx")

    assert metadata["content_code"] == "isdr"
    assert metadata["channel_or_format"] == "wa"
    assert metadata["language"] == "en"
    assert metadata["section_code"] == "1f"
    assert metadata["version"] == "v1"
    assert metadata["document_stage"] == "Base Doc"
    assert metadata["title"] == "Identify Spurious Medicines"
    assert metadata["original_filename"] == "isdr_wa_en_1f_v1- Base Doc - Identify Spurious Medicines.docx"


def test_parse_base_doc_suffix_variation() -> None:
    metadata = parse_filename("rume_wa_en_1h_v1-Where can I return Medical waste-Base Doc.docx")

    assert metadata["document_stage"] == "Base Doc"
    assert metadata["title"] == "Where can I return Medical waste"


def test_parse_fallback() -> None:
    metadata = parse_filename("Unstructured Name.pdf")

    assert metadata == {
        "original_filename": "Unstructured Name.pdf",
        "title": "Unstructured Name",
    }
