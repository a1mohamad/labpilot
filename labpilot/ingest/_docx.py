from __future__ import annotations

import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

from labpilot.ingest.defaults import MAX_DOCX_XML_BYTES
from labpilot.ingest.errors import LoaderError

# Not a URL anybody fetches -- an XML namespace is a unique name, and
# ElementTree stores it as part of every tag.
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PARAGRAPH = f"{WORD}p"
TEXT = f"{WORD}t"
TAB = f"{WORD}tab"
BREAK = f"{WORD}br"

DOCUMENT = "word/document.xml"


def load_docx(raw: bytes) -> str:
    root = _document(raw)
    paragraphs = (_paragraph(node) for node in root.iter(PARAGRAPH))
    # A blank line between paragraphs is what lets split_recursive break on a
    # paragraph rather than mid-sentence: "\n\n" is its second separator.
    return "\n\n".join(text for text in paragraphs if text.strip())


def _document(raw: bytes) -> ET.Element:
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            xml = _read_within_limit(archive)
    except zipfile.BadZipFile as exc:
        raise LoaderError(
            f"not a Word file: a .docx is a ZIP, and this is not ({exc})"
        ) from exc
    except KeyError as exc:
        raise LoaderError(
            f"a ZIP with no {DOCUMENT}: this is some other Office file, "
            f"not a Word document"
        ) from exc

    try:
        return ET.fromstring(xml)
    except ET.ParseError as exc:
        raise LoaderError(f"{DOCUMENT} is not valid XML: {exc}") from exc


def _read_within_limit(archive: zipfile.ZipFile) -> bytes:
    # A .docx is a ZIP, so it can be a decompression bomb. Measured: real
    # papers hold 55KB-266KB of document.xml, while 48KB of crafted archive
    # expands to 50MB. getinfo reads the header only, so the size is known
    # before a single byte is decompressed.
    declared = archive.getinfo(DOCUMENT).file_size
    if declared > MAX_DOCX_XML_BYTES:
        raise LoaderError(
            f"{DOCUMENT} unpacks to {declared} bytes, over the "
            f"{MAX_DOCX_XML_BYTES} limit: a Word file that expands this far "
            f"is a decompression bomb, not a document"
        )

    return archive.read(DOCUMENT)


def _paragraph(paragraph: ET.Element) -> str:
    # Word splits one sentence across several runs whenever the formatting
    # changes. Measured on a real paper: 15 runs for one line of code, and a
    # paragraph whose first two runs are "T" and "his paper". Joining with
    # anything but "" puts a space inside the word.
    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == TEXT:
            parts.append(node.text or "")
        elif node.tag == TAB:
            parts.append("\t")
        elif node.tag == BREAK:
            parts.append("\n")

    return "".join(parts)
