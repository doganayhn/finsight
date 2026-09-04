"""Construct synthetic PDF bytes in memory using only pypdf; never read a real PDF."""

from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def synthetic_pdf(pages: list[str], *, encrypted=False) -> bytes:
    writer = PdfWriter()
    # A one-byte font map preserves the independently authored Turkish fixture text.
    characters = sorted(set("".join(pages)) - {"\n", "\r"})
    assert len(characters) < 256
    mapping = {char: index for index, char in enumerate(characters, 1)}
    cmap = DecodedStreamObject()
    pairs = "\n".join(f"<{code:02X}> <{ord(char):04X}>" for char, code in mapping.items())
    cmap.set_data(
        (
            "/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
            "/CIDSystemInfo << /Registry (Synthetic) /Ordering (Test) /Supplement 0 >> def\n"
            "/CMapName /Synthetic def /CMapType 2 def\n"
            "1 begincodespacerange <00> <FF> endcodespacerange\n"
            f"{len(mapping)} beginbfchar\n{pairs}\nendbfchar\n"
            "endcmap CMapName currentdict /CMap defineresource pop end end"
        ).encode("ascii")
    )
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/ToUnicode"): writer._add_object(cmap),
        }
    )
    font_ref = writer._add_object(font)
    for page_text in pages:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
        content = ["BT /F1 10 Tf 14 TL 40 750 Td"]
        for line in page_text.splitlines():
            encoded = bytes(mapping[char] for char in line).hex()
            content.append(f"<{encoded}> Tj T*")
        content.append("ET")
        stream = DecodedStreamObject()
        stream.set_data("\n".join(content).encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("synthetic-test-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
