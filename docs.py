"""Documents, spreadsheets, presentations, data, web, archive, email, blocked-extension and filename test files.

Imported by generate.py (which passes itself in as `g`). Everything is tiny and hand-built where possible:
PDF and OOXML (docx/xlsx) are written directly, pptx uses python-pptx, and the legacy / OpenDocument formats
(doc, odt, rtf, xls, ods, ppt, odp) are converted from them with LibreOffice. Password for protected files: qa-example
"""
import base64, gzip, io, json, re, shutil, subprocess, tarfile, tempfile, threading, zipfile, zlib
from pathlib import Path
from xml.sax.saxutils import escape

BRAND = "qa-example"
PASSWORD = "qa-example"
ZIP_DATE = (2026, 1, 1, 0, 0, 0)
SOFFICE = (shutil.which("soffice") or shutil.which("libreoffice")
           or next((c for c in ("/Applications/LibreOffice.app/Contents/MacOS/soffice", "/opt/homebrew/bin/soffice",
                                "/usr/local/bin/soffice", "/usr/bin/soffice") if Path(c).exists()), "soffice"))
COL = {"document": (0, 102, 204), "spreadsheet": (0, 153, 76), "presentation": (255, 120, 0)}
GROUPS = {"document": "DocumentQAExamples", "spreadsheet": "SpreadsheetQAExamples",
          "presentation": "PresentationQAExamples", "data": "DataQAExamples", "web": "WebQAExamples",
          "archive": "ArchiveQAExamples", "email": "EmailQAExamples", "blocked": "BlockedExtensionQAExamples",
          "filename": "FilenameQAExamples"}


def hexc(c):
    return "%02X%02X%02X" % c


def label(kind, fmt, desc):
    return f"{BRAND} | {kind.upper()} {fmt.upper()} | {desc}"


# ---------------------------------------------------------------- PDF
def _pdf_esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(n_pages, colour=COL["document"]):
    r, gr, b = (c / 255 for c in colour)
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"}
    kids = []
    for i in range(n_pages):
        pid, cid = 5 + 2 * i, 6 + 2 * i
        kids.append(f"{pid} 0 R")
        body = (f"{r:.3f} {gr:.3f} {b:.3f} RG 18 w 24 24 547 794 re S\n"
                f"BT /F2 34 Tf 0 g 70 700 Td (DOCUMENT PDF) Tj ET\n"
                f"BT /F1 22 Tf 0 g 70 655 Td ({n_pages} page{'s' if n_pages > 1 else ''}) Tj ET\n"
                f"BT /F1 18 Tf 0 g 70 620 Td (page {i + 1} of {n_pages}) Tj ET\n"
                f"BT /F1 14 Tf 0.75 g 70 780 Td ({BRAND}) Tj ET\n").encode()
        comp = zlib.compress(body, 9)
        objs[pid] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {cid} 0 R "
                     f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>").encode()
        objs[cid] = f"<< /Length {len(comp)} /Filter /FlateDecode >>\nstream\n".encode() + comp + b"\nendstream"
    objs[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {n_pages} >>".encode()
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for n in sorted(objs):
        offsets[n] = len(out)
        out += f"{n} 0 obj\n".encode() + objs[n] + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for n in sorted(objs):
        out += f"{offsets[n]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def make_pdf_image_only(g):
    img = g.label_frame(COL["document"], 595, 842, ["DOCUMENT PDF", "image only (scanned)"])[0].quantize(16)
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=72)
    return buf.getvalue()


def make_pdf_password():
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf(1))))
    w.encrypt(PASSWORD, algorithm="AES-256")
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- OOXML (docx, xlsx) and pptx
def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in files:
            z.writestr(zipfile.ZipInfo(name, ZIP_DATE), data, zipfile.ZIP_DEFLATED, 9)
    return buf.getvalue()


CT_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OD_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _root_rels(target):
    return (f'{CT_HEAD}<Relationships xmlns="{RELS_NS}"><Relationship Id="rId1" '
            f'Type="{OD_REL}/officeDocument" Target="{target}"/></Relationships>')


def make_docx(fmt_label, n_pages, colour=COL["document"]):
    c = hexc(colour)

    def para(text, size, color="000000", bold=False):
        return (f'<w:p><w:r><w:rPr>{"<w:b/>" if bold else ""}<w:color w:val="{color}"/><w:sz w:val="{size}"/></w:rPr>'
                f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')
    body = []
    for i in range(n_pages):
        if i:
            body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        body += [para(BRAND, 22, "BFBFBF"), para(f"DOCUMENT {fmt_label}", 56, c, True),
                 para(f"{n_pages} page{'s' if n_pages > 1 else ''}", 32), para(f"page {i + 1} of {n_pages}", 24)]
    edge = f'w:val="single" w:sz="48" w:space="24" w:color="{c}"'
    sect = (f'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" '
            f'w:left="1440" w:header="708" w:footer="708" w:gutter="0"/><w:pgBorders w:offsetFrom="page">'
            f'<w:top {edge}/><w:left {edge}/><w:bottom {edge}/><w:right {edge}/></w:pgBorders></w:sectPr>')
    doc = (f'{CT_HEAD}<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           f'{"".join(body)}{sect}</w:body></w:document>')
    ct = (f'{CT_HEAD}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
          'wordprocessingml.document.main+xml"/></Types>')
    return _zip([("[Content_Types].xml", ct), ("_rels/.rels", _root_rels("word/document.xml")),
                 ("word/document.xml", doc)])


def make_xlsx(fmt_label, sheets, rows=0, colour=COL["spreadsheet"]):
    c = hexc(colour)

    def cell(ref, v, style=0):
        if isinstance(v, (int, float)):
            return f'<c r="{ref}" s="{style}"><v>{v}</v></c>'
        return f'<c r="{ref}" t="inlineStr" s="{style}"><is><t>{escape(str(v))}</t></is></c>'

    def sheet_xml(i):
        data = [(["SPREADSHEET", fmt_label, f"sheet {i} of {sheets}" if sheets > 1 else "1 sheet"], 1), ([BRAND], 2)]
        if rows:
            data += [(["id", "name", "value"], 0)] + [([n, f"row {n}", n * 10], 0) for n in range(1, rows + 1)]
        out = []
        for r, (vals, st) in enumerate(data, 1):
            out.append(f'<row r="{r}">' + "".join(cell(f"{'ABC'[k]}{r}", v, st) for k, v in enumerate(vals)) + "</row>")
        return (f'{CT_HEAD}<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<cols><col min="1" max="3" width="18" customWidth="1"/></cols><sheetData>{"".join(out)}</sheetData></worksheet>')
    styles = (f'{CT_HEAD}<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font>'
              '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
              '<font><sz val="11"/><color rgb="FFBFBFBF"/><name val="Calibri"/></font></fonts>'
              '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
              f'<fill><patternFill patternType="solid"><fgColor rgb="FF{c}"/><bgColor indexed="64"/></patternFill></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
              '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs></styleSheet>')
    wb = (f'{CT_HEAD}<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          f'xmlns:r="{OD_REL}"><sheets>' +
          "".join(f'<sheet name="Sheet{i}" sheetId="{i}" r:id="rId{i}"/>' for i in range(1, sheets + 1)) + "</sheets></workbook>")
    wb_rels = (f'{CT_HEAD}<Relationships xmlns="{RELS_NS}">' +
               "".join(f'<Relationship Id="rId{i}" Type="{OD_REL}/worksheet" Target="worksheets/sheet{i}.xml"/>'
                       for i in range(1, sheets + 1)) +
               f'<Relationship Id="rId{sheets + 1}" Type="{OD_REL}/styles" Target="styles.xml"/></Relationships>')
    ct = (f'{CT_HEAD}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
          "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.'
                  f'spreadsheetml.worksheet+xml"/>' for i in range(1, sheets + 1)) + "</Types>")
    files = [("[Content_Types].xml", ct), ("_rels/.rels", _root_rels("xl/workbook.xml")), ("xl/workbook.xml", wb),
             ("xl/_rels/workbook.xml.rels", wb_rels), ("xl/styles.xml", styles)]
    files += [(f"xl/worksheets/sheet{i}.xml", sheet_xml(i)) for i in range(1, sheets + 1)]
    return _zip(files)


def slim_pptx(data):
    """Drop the printer-settings blob and thumbnail python-pptx's template carries."""
    zin = zipfile.ZipFile(io.BytesIO(data))
    files = []
    for info in zin.infolist():
        name = info.filename
        if "printerSettings" in name or "thumbnail" in name:
            continue
        body = zin.read(name)
        if name.endswith(".rels"):
            body = re.sub(rb'<Relationship [^>]*(?:printerSettings|thumbnail)[^>]*/>', b"", body)
        files.append((name, body))
    return _zip(files)


def slim_odf(data):
    """Drop the thumbnail, settings and rdf parts LibreOffice adds to odt/ods/odp (and their manifest entries)."""
    drop = re.compile(r"^(Thumbnails/|Configurations2/|settings\.xml$|manifest\.rdf$)")
    zin = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for info in zin.infolist():
            if drop.match(info.filename):
                continue
            body = zin.read(info.filename)
            if info.filename == "META-INF/manifest.xml":
                body = re.sub(rb'\s*<manifest:file-entry[^>]*manifest:full-path="(?:Thumbnails/|Configurations2/|settings\.xml|manifest\.rdf)[^"]*"[^>]*/>',
                              b"", body)
            z.writestr(zipfile.ZipInfo(info.filename, ZIP_DATE), body,
                       zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED, 9)
    return out.getvalue()


def make_pptx(fmt_label, n_slides, colour=COL["presentation"]):
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Pt
    prs = Presentation()
    for lay in list(prs.slide_layouts):   # keep only the blank layout: smaller file, and a smaller .ppt
        if lay.name != "Blank":
            prs.slide_layouts.remove(lay)
    for i in range(n_slides):
        s = prs.slides.add_slide(prs.slide_layouts[0])
        w, h = prs.slide_width, prs.slide_height
        edge = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(10), Pt(10), w - Pt(20), h - Pt(20))
        edge.fill.background()
        edge.line.color.rgb = RGBColor(*colour)
        edge.line.width = Pt(14)
        for j, (text, size, rgb) in enumerate([(BRAND, 16, (191, 191, 191)), (f"PRESENTATION {fmt_label}", 36, (0, 0, 0)),
                                               (f"{n_slides} slide{'s' if n_slides > 1 else ''}", 24, (0, 0, 0)),
                                               (f"slide {i + 1} of {n_slides}", 20, (0, 0, 0))]):
            tb = s.shapes.add_textbox(Pt(40), Pt(30 + j * 70 if j else 30), w - Pt(80), Pt(50))
            run = tb.text_frame.paragraphs[0].add_run()
            run.text = text
            run.font.size = Pt(size)
            run.font.bold = j == 1
            run.font.color.rgb = RGBColor(*rgb)
    buf = io.BytesIO()
    prs.save(buf)
    return slim_pptx(buf.getvalue())


# ---------------------------------------------------------------- LibreOffice conversions (built once, cached)
OFFICE = {  # group -> (source ext, converted targets, {variant: count}, builder(label, count))
    "document": ("docx", ["doc", "odt", "rtf"], {"1_page": 1, "10_pages": 10}, lambda lb, n: make_docx(lb, n)),
    "spreadsheet": ("xlsx", ["xls", "ods"], {"1_sheet": (1, 0), "3_sheets": (3, 0), "100_rows": (1, 100)},
                    lambda lb, n: make_xlsx(lb, n[0], n[1])),
    "presentation": ("pptx", ["ppt", "odp"], {"1_slide": 1, "5_slides": 5}, lambda lb, n: make_pptx(lb, n)),
}
_office_lock = threading.Lock()
_office = {}


def office_file(group, fmt, variant):
    with _office_lock:
        if not _office:
            _build_office()
        return _office[(group, fmt, variant)]


def _build_office():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for group, (src, targets, variants, build) in OFFICE.items():
            for fmt in [src] + targets:
                (d / group / fmt).mkdir(parents=True)
                for variant, n in variants.items():
                    data = build(fmt.upper(), n)
                    (d / group / fmt / f"{variant}.{src}").write_bytes(data)
                    if fmt == src:
                        _office[(group, fmt, variant)] = data
            for fmt in targets:
                inp = sorted((d / group / fmt).glob(f"*.{src}"))
                out = d / group / f"out_{fmt}"
                r = subprocess.run([SOFFICE, "--headless", "--norestore", f"-env:UserInstallation=file://{d}/profile",
                                    "--convert-to", fmt, "--outdir", str(out), *map(str, inp)],
                                   capture_output=True)
                for variant in variants:
                    f = out / f"{variant}.{fmt}"
                    if not f.exists():
                        raise RuntimeError(f"soffice failed for {group} {fmt} {variant}: {r.stderr.decode()[-200:]}")
                    _office[(group, fmt, variant)] = slim_odf(f.read_bytes()) if fmt in ("odt", "ods", "odp") else f.read_bytes()


# ---------------------------------------------------------------- text / data / web / email
def csv_text(rows, delim=","):
    def q(v):
        v = str(v)
        return '"' + v.replace('"', '""') + '"' if any(ch in v for ch in (delim, '"', "\n")) else v
    return "\n".join(delim.join(q(v) for v in r) for r in rows) + "\n"


def table(n, delim=","):
    return csv_text([["id", "name", "value"]] + [[i, f"{BRAND} row {i}", i * 10] for i in range(1, n + 1)], delim)


HTML_HEAD = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>%s</title>\n</head>\n'
             '<body style="font-family:Arial,sans-serif;border:12px solid #00aaaa;padding:20px">\n')

TEXT = {
    "txt/txt_ascii.txt": lambda: f"{label('document', 'txt', 'plain ASCII')}\nline 2\nline 3\n".encode(),
    "txt/txt_utf8_unicode.txt": lambda: (f"{label('document', 'txt', 'UTF-8 unicode')}\n"
                                         "accents: café señor Zoë | Japanese: 日本語 | Russian: русский | emoji: 😀\n").encode(),
    "txt/txt_utf8_bom.txt": lambda: b"\xef\xbb\xbf" + f"{label('document', 'txt', 'UTF-8 with BOM')}\n".encode(),
    "txt/txt_utf16le.txt": lambda: ("﻿" + f"{label('document', 'txt', 'UTF-16 LE with BOM')}\n").encode("utf-16-le"),
    "txt/txt_crlf.txt": lambda: f"{label('document', 'txt', 'Windows CRLF')}\r\nline 2\r\nline 3\r\n".encode(),
    "txt/txt_empty_0_bytes.txt": lambda: b"",
    "md/md_basic.md": lambda: (f"# DOCUMENT MD\n\n{BRAND} | markdown\n\n- item 1\n- item 2\n\n**bold** and `code`\n").encode(),
    "csv/csv_3_rows.csv": lambda: table(3).encode(),
    "csv/csv_100_rows.csv": lambda: table(100).encode(),
    "csv/csv_1000_rows.csv": lambda: table(1000).encode(),
    "csv/csv_utf8_bom.csv": lambda: b"\xef\xbb\xbf" + csv_text([["id", "name"], [1, "café"], [2, "日本語"], [3, "русский"]]).encode(),
    "csv/csv_semicolon.csv": lambda: csv_text([["id", "name", "value"], [1, f"{BRAND} one", "1,5"], [2, f"{BRAND} two", "2,5"]], ";").encode(),
    "csv/csv_quoted_fields.csv": lambda: csv_text([["id", "text"], [1, "has, comma"], [2, 'has "quotes"'], [3, "has\nnewline"]]).encode(),
    "csv/csv_header_only.csv": lambda: b"id,name,value\n",
    "csv/csv_empty_0_bytes.csv": lambda: b"",
    "tsv/tsv_3_rows.tsv": lambda: table(3, "\t").encode(),
    "tsv/tsv_100_rows.tsv": lambda: table(100, "\t").encode(),
    "json/json_object.json": lambda: (json.dumps({"qa-example": "DATA JSON", "description": "object", "id": 1}, indent=2) + "\n").encode(),
    "json/json_array_100.json": lambda: (json.dumps([{"id": i, "name": f"{BRAND} {i}"} for i in range(1, 101)]) + "\n").encode(),
    "json/json_nested.json": lambda: (json.dumps({"qa-example": "DATA JSON", "a": {"b": {"c": [1, 2, {"d": None, "e": True}]}}}, indent=2) + "\n").encode(),
    "json/json_empty_object.json": lambda: b"{}\n",
    "json/json_invalid.json": lambda: b'{"qa-example": "DATA JSON invalid", "missing_closing_brace": true\n',
    "xml/xml_basic.xml": lambda: (f'<?xml version="1.0" encoding="UTF-8"?>\n<qa-example format="xml" description="basic">'
                                  f'<item id="1">one</item><item id="2">two</item></qa-example>\n').encode(),
    "xml/xml_nested.xml": lambda: ('<?xml version="1.0" encoding="UTF-8"?>\n<qa-example format="xml" description="nested">'
                                   '<a><b><c attr="1">deep</c></b></a><!-- comment --><![CDATA[raw <text>]]></qa-example>\n').encode(),
    "xml/xml_invalid.xml": lambda: b'<?xml version="1.0"?>\n<qa-example format="xml" description="invalid"><unclosed>\n',
    "yaml/yaml_basic.yaml": lambda: f"qa-example: DATA YAML\ndescription: basic\nitems:\n  - one\n  - two\n".encode(),
    "sql/sql_inserts.sql": lambda: ("-- qa-example | DATA SQL | inserts\nCREATE TABLE qa_example (id INT, name VARCHAR(50));\n"
                                    "INSERT INTO qa_example VALUES (1, 'one');\nINSERT INTO qa_example VALUES (2, 'two');\n").encode(),
    "ndjson/ndjson_3_lines.ndjson": lambda: "".join(json.dumps({"id": i, "qa-example": "DATA NDJSON"}) + "\n" for i in range(1, 4)).encode(),
    "html/html_basic.html": lambda: (HTML_HEAD % "qa-example HTML basic" + '<h1>WEB HTML</h1>\n<p>basic page</p>\n'
                                     '<p style="color:#bbb">qa-example</p>\n</body>\n</html>\n').encode(),
    "html/html_form.html": lambda: (HTML_HEAD % "qa-example HTML form" + '<h1>WEB HTML</h1>\n<form action="#" method="post">\n'
                                    '<label>Name <input name="name"></label>\n<input type="file" name="upload">\n'
                                    '<button type="submit">Submit</button>\n</form>\n<p style="color:#bbb">qa-example</p>\n</body>\n</html>\n').encode(),
    "html/html_unicode.html": lambda: (HTML_HEAD % "qa-example HTML unicode" + '<h1>WEB HTML</h1>\n<p>café | 日本語 | русский | 😀</p>\n'
                                       '<p style="color:#bbb">qa-example</p>\n</body>\n</html>\n').encode(),
    "css/css_basic.css": lambda: b"/* qa-example | WEB CSS */\nbody { font-family: Arial, sans-serif; border: 12px solid #00aaaa; }\n",
    "js/js_basic.js": lambda: b'// qa-example | WEB JS\nconsole.log("qa-example");\n',
    "eml/eml_basic.eml": lambda: ("From: qa-example <from@example.com>\r\nTo: you <to@example.com>\r\nSubject: qa-example EMAIL EML basic\r\n"
                                  "Date: Thu, 01 Jan 2026 00:00:00 +0000\r\nMIME-Version: 1.0\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
                                  "qa-example | EMAIL EML | basic\r\n").encode(),
    "eml/eml_with_attachment.eml": lambda: (
        "From: qa-example <from@example.com>\r\nTo: you <to@example.com>\r\nSubject: qa-example EMAIL EML attachment\r\n"
        "Date: Thu, 01 Jan 2026 00:00:00 +0000\r\nMIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary=\"qa-example-boundary\"\r\n\r\n"
        "--qa-example-boundary\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nqa-example | EMAIL EML | with attachment\r\n"
        "--qa-example-boundary\r\nContent-Type: text/plain; name=\"attachment.txt\"\r\nContent-Transfer-Encoding: base64\r\n"
        "Content-Disposition: attachment; filename=\"attachment.txt\"\r\n\r\n"
        + base64.b64encode(b"qa-example attachment\n").decode() + "\r\n--qa-example-boundary--\r\n").encode(),
    "ics/ics_event.ics": lambda: ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//qa-example//EN\r\nBEGIN:VEVENT\r\nUID:qa-example-1@example.com\r\n"
                                  "DTSTAMP:20260101T000000Z\r\nDTSTART:20260102T090000Z\r\nDTEND:20260102T100000Z\r\n"
                                  "SUMMARY:qa-example EMAIL ICS event\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n").encode(),
    "vcf/vcf_contact.vcf": lambda: ("BEGIN:VCARD\r\nVERSION:3.0\r\nFN:qa-example Contact\r\nN:Contact;qa-example;;;\r\n"
                                    "EMAIL:contact@example.com\r\nNOTE:qa-example EMAIL VCF contact\r\nEND:VCARD\r\n").encode(),
}

BLOCKED = {  # harmless content, risky extension (for upload blocklist tests)
    "exe": b"qa-example: harmless text file with an .exe extension. Not an executable.\n",
    "dll": b"qa-example: harmless text file with a .dll extension. Not a library.\n",
    "bat": b"@echo off\r\nrem qa-example: harmless test file\r\necho qa-example\r\n",
    "sh": b'#!/bin/sh\n# qa-example: harmless test file\necho "qa-example"\n',
    "php": b'<?php // qa-example: harmless test file, does nothing ?>\n',
}


# ---------------------------------------------------------------- archives
def zip_bytes(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            z.writestr(zipfile.ZipInfo(name, ZIP_DATE), data, zipfile.ZIP_DEFLATED, 9)
    return buf.getvalue()


def files3(prefix=""):
    return [(f"{prefix}file{i}.txt", f"{label('archive', 'file', f'file {i} of 3')}\n".encode()) for i in (1, 2, 3)]


def zip_password():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "qa-example.txt").write_text(f"{label('archive', 'zip', 'password protected')}\n")
        subprocess.run(["zip", "-q", "-X", "-P", PASSWORD, "out.zip", "qa-example.txt"], cwd=d, check=True)
        return (Path(d) / "out.zip").read_bytes()


def tar_bytes(gz=False):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for name, data in files3():
            ti = tarfile.TarInfo(name)
            ti.size, ti.mtime = len(data), 1767225600
            t.addfile(ti, io.BytesIO(data))
    raw = buf.getvalue()
    end = -(-len(raw.rstrip(b"\0")) // 512) * 512          # tar pads to 10 KB by default; 2 zero blocks is enough
    raw = raw[:end] + bytes(1024)
    return gzip.compress(raw, 9, mtime=0) if gz else raw


def sevenz_bytes():
    import py7zr
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out.7z"
        with py7zr.SevenZipFile(out, "w") as z:
            for name, data in files3():
                z.writestr(data, name)
        return out.read_bytes()


def gz_bytes():
    return gzip.compress(f"{label('archive', 'gz', 'single file')}\n".encode(), 9, mtime=0)


def epub_bytes():
    xhtml = ('<?xml version="1.0" encoding="UTF-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml" '
             'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>qa-example</title></head><body>'
             '<h1>DOCUMENT EPUB</h1><p>qa-example</p><nav epub:type="toc"><ol><li><a href="c1.xhtml">chapter 1</a></li></ol></nav></body></html>')
    opf = ('<?xml version="1.0" encoding="UTF-8"?>\n<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">qa-example-epub</dc:identifier>'
           '<dc:title>qa-example DOCUMENT EPUB</dc:title><dc:language>en</dc:language>'
           '<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta></metadata><manifest>'
           '<item id="c1" href="c1.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest>'
           '<spine><itemref idref="c1"/></spine></package>')
    cont = ('<?xml version="1.0"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
            '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype", ZIP_DATE), "application/epub+zip", zipfile.ZIP_STORED)
        for name, data in [("META-INF/container.xml", cont), ("OEBPS/content.opf", opf), ("OEBPS/c1.xhtml", xhtml)]:
            z.writestr(zipfile.ZipInfo(name, ZIP_DATE), data, zipfile.ZIP_DEFLATED, 9)
    return buf.getvalue()


def filename_files():
    text = lambda name: f"{label('filename', 'txt', name)}\n".encode()
    names = ["file with spaces.txt", "unicode_日本語_русский_café.txt", "UPPERCASE_EXTENSION.TXT", "no_extension",
             "multiple.dots.in.the.name.v1.2.txt", "special_chars_(1)_[2]_&_+_#_%.txt", "double_extension.jpg.txt",
             "long_name_100_chars_" + "a" * 77 + ".txt", "long_name_255_chars_" + "a" * 231 + ".txt"]
    return [(n, text(n)) for n in names]


def doc_jobs(g, root, only):
    if "documents" not in only:
        return []
    jobs = []

    def add(group, fmt, name, ext, maker):
        jobs.append((root / GROUPS[group] / fmt / f"{name}.{ext}", lambda p, m=maker: p.write_bytes(m())))

    for key, maker in TEXT.items():
        fmt, name = key.split("/")
        group = {"txt": "document", "md": "document", "csv": "spreadsheet", "tsv": "spreadsheet",
                 "eml": "email", "ics": "email", "vcf": "email"}.get(fmt, "web" if fmt in ("html", "css", "js") else "data")
        add(group, fmt, name.rsplit(".", 1)[0], name.rsplit(".", 1)[1], maker)
    add("document", "pdf", "pdf_1_page", "pdf", lambda: make_pdf(1))
    add("document", "pdf", "pdf_10_pages", "pdf", lambda: make_pdf(10))
    add("document", "pdf", "pdf_100_pages", "pdf", lambda: make_pdf(100))
    add("document", "pdf", "pdf_image_only", "pdf", lambda: make_pdf_image_only(g))
    add("document", "pdf", "pdf_password_protected", "pdf", make_pdf_password)
    add("document", "epub", "epub_basic", "epub", epub_bytes)
    for group, (src, targets, variants, _b) in OFFICE.items():
        for fmt in [src] + targets:
            for variant in variants:
                add(group, fmt, f"{fmt}_{variant}", fmt,
                    lambda gr=group, f=fmt, v=variant: office_file(gr, f, v))
    add("archive", "zip", "zip_1_file", "zip", lambda: zip_bytes(files3()[:1]))
    add("archive", "zip", "zip_3_files", "zip", lambda: zip_bytes(files3()))
    add("archive", "zip", "zip_with_folders", "zip", lambda: zip_bytes(files3("folder_a/folder_b/")))
    add("archive", "zip", "zip_nested", "zip", lambda: zip_bytes([("inner.zip", zip_bytes(files3()[:1]))]))
    add("archive", "zip", "zip_empty", "zip", lambda: zip_bytes([]))
    add("archive", "zip", "zip_password_protected", "zip", zip_password)
    add("archive", "tar", "tar_3_files", "tar", tar_bytes)
    add("archive", "tar_gz", "tar_gz_3_files", "tar.gz", lambda: tar_bytes(gz=True))
    add("archive", "gz", "gz_1_file", "gz", gz_bytes)
    add("archive", "7z", "7z_3_files", "7z", sevenz_bytes)
    for ext, data in BLOCKED.items():
        add("blocked", ext, f"{ext}_harmless", ext, lambda d=data: d)
    add("blocked", "jar", "jar_harmless", "jar", lambda: zip_bytes([("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\r\nCreated-By: qa-example\r\n\r\n")]))
    for name, data in filename_files():
        jobs.append((root / GROUPS["filename"] / name, lambda p, d=data: p.write_bytes(d)))
    return jobs
