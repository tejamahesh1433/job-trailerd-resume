"""
Failure-path tests for POST /api/profile/upload — unsupported types, oversized/empty
files, and a corrupt PDF that pdfplumber can't parse (should surface a clean 500,
never a raw traceback or a hang).
"""


def test_upload_rejects_unsupported_extension(client):
    resp = client.post(
        "/api/profile/upload",
        files={"file": ("resume.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


def test_upload_rejects_empty_file(client):
    resp = client.post(
        "/api/profile/upload",
        files={"file": ("resume.pdf", b"", "application/pdf")},
    )
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


def test_upload_rejects_oversized_file(client):
    oversized = b"0" * (10 * 1024 * 1024 + 1)
    resp = client.post(
        "/api/profile/upload",
        files={"file": ("resume.pdf", oversized, "application/pdf")},
    )
    assert resp.status_code == 400
    assert "too large" in resp.json()["detail"].lower()


def test_upload_handles_corrupt_pdf_gracefully(client):
    # Not a real PDF — pdfplumber/pdfminer raises PdfminerException opening it.
    # The endpoint must catch that and return a clean 500, not a raw traceback.
    garbage = b"this is not a real pdf, just garbage bytes pretending to be one"
    resp = client.post(
        "/api/profile/upload",
        files={"file": ("resume.pdf", garbage, "application/pdf")},
    )
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to process document"


def test_upload_requires_a_file(client):
    resp = client.post("/api/profile/upload")
    assert resp.status_code == 422
