#!/usr/bin/env python3
"""qa-example test-data generator.

Layout under --root: manualFiles/ (everything) and automationFiles/ (smallest clip + size of each format).

Every file says what it is. Videos get a thick pink border, images a thick
yellow border, on a plain white background with black text, so a screenshot of
any frame identifies the file. Files are tiny (low quality, flat colour).

Needs: ffmpeg/ffprobe, Pillow, and macOS `sips` (heic only).
Existing files are never overwritten unless --force is given.

Usage: .venv/bin/python generate.py [--root DIR] [--only video,image,audio,...] [--force]   (default output: ./qa-example-data)
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BRAND = "qa-example"          # the small faint title on every video and image
TITLE_ALPHA = 70              # 0-255, black text over white, so the title stays faint
PINK, YELLOW, WHITE, BLACK = (255, 0, 144), (255, 215, 0), (255, 255, 255), (0, 0, 0)
FONT_PATHS = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf"]

VIDEO_SECS = [1, 5]
VIDEO_RES = [(320, 240), (640, 360), (640, 480), (720, 720), (1280, 720), (1920, 1080), (1080, 1920)]
# extra (longer) clips for the most popular formats, at the most popular sizes
LONG_VIDEO = {"mp4": [30], "mov": [30]}
LONG_VIDEO_RES = [(640, 360), (1280, 720), (1920, 1080), (1080, 1920)]
IMAGE_RES = [(160, 120), (640, 480), (800, 600), (1280, 720), (1920, 1080), (1080, 1920)]
BMP_RES = [(160, 120), (320, 240), (640, 480), (800, 600)]
ICO_SIZES = [16, 32, 48, 64, 128, 256]
AUDIO_SECS = [1, 5]

H264 = ["-c:v", "libx264", "-preset", "slow", "-crf", "38", "-g", "150", "-pix_fmt", "yuv420p"]
# fmt -> (extension, codec label, output fps, ffmpeg args)
VIDEO_FORMATS = {
    "mp4":  ("mp4", "h264", None, H264 + ["-movflags", "+faststart"]),
    "m4v":  ("m4v", "h264", None, H264 + ["-f", "ipod", "-movflags", "+faststart"]),
    "mov":  ("mov", "h264", None, H264 + ["-movflags", "+faststart"]),
    "avi":  ("avi", "h264", None, H264 + ["-bf", "0"]),
    "mkv":  ("mkv", "h264", None, H264),
    "webm": ("webm", "vp9", None, ["-c:v", "libvpx-vp9", "-crf", "50", "-b:v", "0", "-g", "150",
                                   "-deadline", "good", "-cpu-used", "5", "-pix_fmt", "yuv420p"]),
    "mpeg": ("mpeg", "mpeg2", 25, ["-c:v", "mpeg2video", "-q:v", "20", "-g", "25", "-pix_fmt", "yuv420p", "-f", "mpeg"]),
    "wmv":  ("wmv", "wmv2", None, ["-c:v", "wmv2", "-b:v", "150k", "-pix_fmt", "yuv420p"]),
    "flv":  ("flv", "h264", None, H264 + ["-bf", "0"]),
    "3gp":  ("3gp", "h264", None, H264),
    "mxf":  ("mxf", "mpeg2", 25, ["-c:v", "mpeg2video", "-q:v", "10", "-g", "12", "-bf", "0", "-pix_fmt", "yuv422p", "-f", "mxf"]),
    "ts":   ("ts", "h264", None, H264),
}
# audio track for the "with audio" video variants: fmt -> (audio codec label, ffmpeg args)
AAC = ["-c:a", "aac", "-b:a", "32k", "-ar", "48000"]
VIDEO_AUDIO = {
    "mp4": ("aac", AAC), "m4v": ("aac", AAC), "mov": ("aac", AAC), "mkv": ("aac", AAC),
    "3gp": ("aac", AAC), "ts": ("aac", AAC), "flv": ("aac", AAC),
    "avi": ("mp3", ["-c:a", "libmp3lame", "-b:a", "32k", "-ar", "44100"]),
    "webm": ("opus", ["-c:a", "libopus", "-b:a", "24k", "-ar", "48000"]),
    "mpeg": ("mp2", ["-c:a", "mp2", "-b:a", "64k", "-ar", "48000"]),
    "wmv": ("wmav2", ["-c:a", "wmav2", "-b:a", "32k", "-ar", "44100"]),
    "mxf": ("pcm", ["-c:a", "pcm_s16le", "-ar", "48000"]),
}
# fmt -> (extension, ffmpeg args)
AUDIO_FORMATS = {
    "mp3":  ("mp3", ["-ar", "22050", "-c:a", "libmp3lame", "-b:a", "24k"]),
    "wav":  ("wav", ["-ar", "8000", "-c:a", "pcm_s16le"]),
    "flac": ("flac", ["-ar", "8000", "-c:a", "flac"]),
    "ogg":  ("ogg", ["-ar", "24000", "-c:a", "libopus", "-b:a", "16k"]),
    "opus": ("opus", ["-ar", "24000", "-c:a", "libopus", "-b:a", "16k"]),
    "m4a":  ("m4a", ["-ar", "22050", "-c:a", "aac", "-b:a", "24k"]),
    "aac":  ("aac", ["-ar", "22050", "-c:a", "aac", "-b:a", "24k"]),
    "aiff": ("aiff", ["-ar", "8000", "-c:a", "pcm_s16be"]),
    "wma":  ("wma", ["-ar", "22050", "-c:a", "wmav2", "-b:a", "24k"]),
}


def font(size):
    for p in FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def label_frame(border, w, h, lines, title_top=False):
    """Thick coloured border, white inside, black centred text, faint title. Returns (image, inner border width)."""
    t = max(6, min(w, h) // 14)
    img = Image.new("RGB", (w, h), border)
    d = ImageDraw.Draw(img)
    d.rectangle([t, t, w - t - 1, h - t - 1], fill=WHITE)
    inner_w, inner_h = w - 2 * t, h - 2 * t
    size = max(8, min(inner_h // (len(lines) * 2), 200))
    f = font(size)
    while size > 8 and max(d.textlength(s, font=f) for s in lines) > inner_w * 0.92:
        size -= 2
        f = font(size)
    lh = int(size * 1.3)
    y = (h - lh * len(lines)) // 2 + int(size * 0.1)
    for s in lines:
        d.text(((w - d.textlength(s, font=f)) / 2, y), s, font=f, fill=BLACK)
        y += lh
    ws = max(8, min(h // 16, 30))
    wf = font(ws)
    while ws > 8 and d.textlength(BRAND, font=wf) > inner_w * 0.5:
        ws -= 1
        wf = font(ws)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    wy = t + ws * 0.4 if title_top else h - t - ws * 1.7
    ImageDraw.Draw(overlay).text(((w - d.textlength(BRAND, font=wf)) / 2, wy), BRAND,
                                 font=wf, fill=(0, 0, 0, TITLE_ALPHA))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"), t


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace").strip().splitlines()[-1])


def make_video(path, fmt, w, h, secs, audio=False, caption=None):
    """audio: add a quiet 440Hz tone track. caption: replaces the second label line."""
    ext, codec, out_fps, args = VIDEO_FORMATS[fmt]
    fps = 5
    alabel = VIDEO_AUDIO[fmt][0] if audio else None
    lines = [f"VIDEO {fmt.upper()} {w}x{h}",
             caption or f"{secs} sec | {codec} | {alabel + ' audio' if audio else 'no audio'}"]
    base, t = label_frame(PINK, w, h, lines, title_top=True)
    n = secs * fps
    cf = font(max(10, h // 28))
    title = f"{BRAND} VIDEO {fmt.upper()} {w}x{h} {secs} sec"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
           *(["-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}:sample_rate=48000"] if audio else []),
           *args, *(["-map", "0:v", "-map", "1:a", "-af", "volume=0.3", "-ac", "1", *VIDEO_AUDIO[fmt][1],
                     "-shortest"] if audio else ["-an"]),
           *(["-r", str(out_fps)] if out_fps else []), "-metadata", f"title={title}", str(path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for i in range(n):
            fr = base.copy()
            ImageDraw.Draw(fr).text((t + 4, h - t - cf.size * 1.5), f"t={i / fps:.1f}s frame {i + 1}/{n}", font=cf, fill=BLACK)
            p.stdin.write(fr.tobytes())
        p.stdin.close()
    except BrokenPipeError:
        pass
    err = p.stderr.read().decode(errors="replace").strip()
    if p.wait():
        raise RuntimeError(err.splitlines()[-1] if err else "ffmpeg failed")


def make_audio(path, fmt, secs):
    ext, args = AUDIO_FORMATS[fmt]
    title = f"{BRAND} AUDIO {fmt.upper()} {secs} sec 440Hz tone"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         f"sine=frequency=440:duration={secs}", "-af", "volume=0.3", "-ac", "1", *args,
         "-metadata", f"title={title}", str(path)])


def image_label(fmt, w, h, extra="low quality"):
    return label_frame(YELLOW, w, h, [f"IMAGE {fmt.upper()} {w}x{h}", extra])[0]


def make_image(path, fmt, w, h, extra="low quality"):
    img = image_label(fmt, w, h, extra)
    if fmt == "jpg":
        img.save(path, quality=25, optimize=True, subsampling=2)
    elif fmt == "png":
        img.quantize(16).save(path, optimize=True)
    elif fmt == "gif":
        img.quantize(16).save(path, optimize=True)
    elif fmt == "bmp":
        img.quantize(16).save(path)
    elif fmt == "tiff":
        img.save(path, compression="tiff_adobe_deflate")
    elif fmt == "webp":
        img.save(path, quality=20, method=6)
    elif fmt == "avif":
        img.save(path, quality=20, speed=6)
    elif fmt == "heic":
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src.png"
            img.save(src)
            run(["sips", "-s", "format", "heic", "-s", "formatOptions", "low", str(src), "--out", str(path)])
    else:
        raise ValueError(fmt)


def make_ico(path, size):
    img = label_frame(YELLOW, 256, 256, ["ICO", f"{size}px"])[0]
    img.save(path, sizes=[(size, size)])


def make_svg(path, w, h):
    t = max(6, min(w, h) // 14)
    fs = max(10, h // 9)
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<rect width="{w}" height="{h}" fill="#ffd700"/>'
        f'<rect x="{t}" y="{t}" width="{w - 2 * t}" height="{h - 2 * t}" fill="#fff"/>'
        f'<g font-family="Arial,sans-serif" font-weight="bold" font-size="{fs}" text-anchor="middle">'
        f'<text x="{w // 2}" y="{h // 2 - fs // 4}">IMAGE SVG {w}x{h}</text>'
        f'<text x="{w // 2}" y="{h // 2 + fs}">vector</text></g>'
        f'<text x="{w // 2}" y="{h - t - fs // 3}" font-family="Arial,sans-serif" font-weight="bold" '
        f'font-size="{max(8, min(h // 16, 30))}" text-anchor="middle" fill-opacity="0.27">{BRAND}</text></svg>\n')


def build_jobs(root, only):
    jobs = []
    if "video" in only:
        for fmt, (ext, *_rest) in VIDEO_FORMATS.items():
            for secs in VIDEO_SECS + LONG_VIDEO.get(fmt, []):
                for w, h in (LONG_VIDEO_RES if secs not in VIDEO_SECS else VIDEO_RES):
                    vc = VIDEO_FORMATS[fmt][1]
                    jobs.append((root / f"VideoQAExamples/{fmt}/{secs}_sec_{fmt}_{vc}_{w}x{h}.{ext}",
                                 lambda p, f=fmt, w=w, h=h, s=secs: make_video(p, f, w, h, s)))
                    if fmt in VIDEO_AUDIO:
                        ac = VIDEO_AUDIO[fmt][0]
                        jobs.append((root / f"VideoQAExamples/{fmt}/{secs}_sec_{fmt}_{vc}_{ac}_{w}x{h}.{ext}",
                                     lambda p, f=fmt, w=w, h=h, s=secs: make_video(p, f, w, h, s, audio=True)))
    if "image" in only:
        for fmt, res in [("jpg", IMAGE_RES), ("png", IMAGE_RES), ("tiff", IMAGE_RES), ("webp", IMAGE_RES),
                         ("heic", IMAGE_RES), ("avif", IMAGE_RES), ("bmp", BMP_RES)]:
            for w, h in res:
                jobs.append((root / f"ImageQAExamples/{fmt}/{fmt}_{w}x{h}.{fmt}",
                             lambda p, f=fmt, w=w, h=h: make_image(p, f, w, h)))
        for w, h in IMAGE_RES[:4]:
            jobs.append((root / f"ImageQAExamples/gif/static/gif_{w}x{h}.gif",
                         lambda p, w=w, h=h: make_image(p, "gif", w, h)))
        for s in ICO_SIZES:
            jobs.append((root / f"ImageQAExamples/ico/ico_{s}x{s}.ico", lambda p, s=s: make_ico(p, s)))
        for w, h in [(160, 120), (800, 600), (1920, 1080)]:
            jobs.append((root / f"ImageQAExamples/svg/svg_{w}x{h}.svg", lambda p, w=w, h=h: make_svg(p, w, h)))
    if "audio" in only:
        for fmt, (ext, _a) in AUDIO_FORMATS.items():
            for secs in AUDIO_SECS:
                jobs.append((root / f"AudioQAExamples/{fmt}/{secs}_sec_{fmt}.{ext}",
                             lambda p, f=fmt, s=secs: make_audio(p, f, s)))
    from extras import extra_jobs
    from docs import doc_jobs
    me = sys.modules[__name__]
    return jobs + extra_jobs(me, root, only) + doc_jobs(me, root, only)


def probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(p)],
                       capture_output=True)
    if r.returncode:
        return {}
    j = json.loads(r.stdout)
    out = {}
    for s in j.get("streams", []):
        if s.get("codec_type") in ("video", "audio") and "codec" not in out.get(s["codec_type"], {}):
            out[s["codec_type"]] = {k: s[k] for k in ("codec_name", "width", "height", "sample_rate") if k in s}
    dur = j.get("format", {}).get("duration")
    if dur:
        out["duration_sec"] = round(float(dur), 2)
    return out


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(root):
    skip = {".DS_Store", "manifest.json", "README.md", ".gitignore"}
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.name not in skip)
    entries = []
    for p in files:
        e = {"path": str(p.relative_to(root)), "bytes": p.stat().st_size, "sha256": sha256_file(p)}
        e.update(probe(p))
        entries.append(e)
    (root / "manifest.json").write_text(json.dumps({"files": entries}, indent=1))
    return entries


AUTOMATION_PICKS = [  # (manualFiles folder, glob) -> automationFiles/<dest>/ ; smallest clip, smallest size
    ("VideoQAExamples", "*/1_sec_*_320x240.*", "video"),
    ("AudioQAExamples", "*/1_sec_*", "audio"),
    ("ImageQAExamples", "[jpbtwha][pnimve]*/*_160x120.*", "image"),   # jpg png bmp tiff webp heic avif
    ("ImageQAExamples", "gif/static/gif_160x120.gif", "image"),
    ("ImageQAExamples", "ico/ico_16x16.ico", "image"),
    ("ImageQAExamples", "svg/svg_160x120.svg", "image"),
]


DOC_PICKS = {  # automationFiles/<dest>/ <- manualFiles/<folder>/*/<name>  (the smallest file of each format)
    "document": ("DocumentQAExamples", ["pdf_1_page.pdf", "pdf_password_protected.pdf", "docx_1_page.docx", "doc_1_page.doc",
                                        "odt_1_page.odt", "rtf_1_page.rtf", "txt_ascii.txt", "md_basic.md", "epub_basic.epub"]),
    "spreadsheet": ("SpreadsheetQAExamples", ["xlsx_1_sheet.xlsx", "xls_1_sheet.xls", "ods_1_sheet.ods", "csv_3_rows.csv",
                                              "csv_empty_0_bytes.csv", "tsv_3_rows.tsv"]),
    "presentation": ("PresentationQAExamples", ["pptx_1_slide.pptx", "odp_1_slide.odp"]),   # no .ppt: LibreOffice embeds a ~600 KB preview
    "data": ("DataQAExamples", ["json_object.json", "json_invalid.json", "xml_basic.xml", "xml_invalid.xml", "yaml_basic.yaml",
                                "sql_inserts.sql", "ndjson_3_lines.ndjson"]),
    "web": ("WebQAExamples", ["html_basic.html", "css_basic.css", "js_basic.js"]),
    "archive": ("ArchiveQAExamples", ["zip_1_file.zip", "zip_password_protected.zip", "tar_3_files.tar", "gz_1_file.gz",
                                      "tar_gz_3_files.tar.gz", "7z_3_files.7z"]),
    "email": ("EmailQAExamples", ["eml_basic.eml", "ics_event.ics", "vcf_contact.vcf"]),
    "blocked": ("BlockedExtensionQAExamples", None),
}


def build_automation(manual, auto, force):
    n = 0
    picks = list(AUTOMATION_PICKS)
    for dest, (folder, names) in DOC_PICKS.items():
        picks += [(folder, f"*/{name}" if names else "*/*", dest) for name in (names or [None])]
    picks.append(("FilenameQAExamples", "*", "filename"))
    for folder, pattern, dest in picks:
        for src in sorted((manual / folder).glob(pattern)):
            if not src.is_file() or len(src.name) > 150:
                continue
            out = auto / dest / src.name
            if force or not out.exists():
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, out)
                n += 1
    return n


README_ROOT = """# qa-example test data

Small, clean, labelled files for testing uploads, players, converters and parsers.
Every video and image shows what it is (format, size, codec), and has a small faint `qa-example` title.
Videos have a thick pink border and images a thick yellow border, so you can tell them apart at a glance.

- `manualFiles/`: everything. Every format, duration (1, 5 and 30 sec), resolution, the exact-size files,
  corrupt and truncated files, and unusual images. For manual testing and exploring.
- `automationFiles/`: one small file per format (1 sec, 320x240 videos, 160x120 images, 1 sec audio),
  in flat folders (`video/`, `image/`, `audio/`, `document/`, `spreadsheet/` and so on).
  Use these in automated tests: they are the smallest and fastest, and every format is still covered.

## What is in manualFiles
`VideoQAExamples`, `ImageQAExamples`, `AudioQAExamples`, `DocumentQAExamples` (pdf, doc, docx, odt, rtf, txt, md, epub),
`SpreadsheetQAExamples` (xls, xlsx, ods, csv, tsv), `PresentationQAExamples` (ppt, pptx, odp),
`DataQAExamples` (json, xml, yaml, sql, ndjson), `WebQAExamples` (html, css, js), `ArchiveQAExamples` (zip, tar, tar.gz, gz, 7z),
`EmailQAExamples` (eml, ics, vcf), `BlockedExtensionQAExamples` (harmless files with risky extensions such as exe and sh),
`FilenameQAExamples` (spaces, unicode, long, double extension), `SizeLimitQAExamples`, `CorruptQAExamples`, `TruncatedQAExamples`.
One folder per format inside each group. Password for the password-protected pdf and zip: `qa-example`.

## File names
- Documents and data: `{format}_{description}.{ext}`, e.g. `pdf_10_pages.pdf`, `csv_100_rows.csv`, `json_invalid.json`.
- Video: `{secs}_sec_{format}_{videocodec}[_{audiocodec}]_{WxH}.{ext}`, e.g. `5_sec_mp4_h264_aac_1280x720.mp4`
  (no audio codec in the name means no audio track).
- Image: `{format}_{WxH}.{ext}`, e.g. `png_800x600.png`.  Audio: `{secs}_sec_{format}.{ext}`.
- Size files: `{format}_{N}MB_exact`, `_plus_1byte`, `_minus_1byte`. 1 MB means 1 MiB (1,048,576 bytes).
- Corrupt and truncated: `corrupt_header_`, `corrupt_body_`, `truncated_50pct_`, `truncated_header_only_`, `empty_0_bytes_`.

## Regenerating
Everything here is made by the `test-data-gen` generator: `python generate.py`. Files over 1 MB (the 5 to 100 MB size files)
are large, so if you only need the small ones, run it with `--only` to skip them.

## Licence
The files in this folder are released under CC0 1.0 (public domain). Use them for anything, no attribution needed.
The generator code is MIT licensed.
"""
README_MANUAL = """# manualFiles

The full set. Browse by type: `VideoQAExamples`, `ImageQAExamples`, `AudioQAExamples`, `SizeLimitQAExamples`
(upload-limit tests), `CorruptQAExamples`, `TruncatedQAExamples`. Under each type there is one folder per format.

`ImageQAExamples/extreme_dimensions` holds tiny files with huge canvases (for example 30000x30000). Many tools refuse
to open these on purpose: they are for testing how your code handles oversized images.
"""
README_AUTOMATION = """# automationFiles

Use these in automated tests. Smallest clip (1 sec) and smallest size of every format, all in flat folders:
`video/` (320x240), `image/` (160x120), `audio/`, and one small folder per document group
(`document/`, `spreadsheet/`, `presentation/`, `data/`, `web/`, `archive/`, `email/`, `blocked/`, `filename/`).
Need a bigger size, longer clip or exact-size file? Take it from `../manualFiles`.
These files are copies of the manualFiles ones, made by the generator: do not edit them by hand.
"""


def write_readmes(root, manual, auto):
    for folder, text in [(root, README_ROOT), (manual, README_MANUAL), (auto, README_AUTOMATION)]:
        (folder / "README.md").write_text(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent / "qa-example-data"),
                    help="output folder (default: qa-example-data next to this script, which is git-ignored)")
    ap.add_argument("--only", default="video,image,audio,sizes,corrupt,imageextras,documents",
                    help="comma list of: video,image,audio,sizes,corrupt,imageextras,documents")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    os.nice(10)
    root = Path(a.root)
    manual, auto = root / "manualFiles", root / "automationFiles"
    only = set(a.only.split(","))
    failed = []

    def work(job):
        p, fn = job
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            fn(p)
            return p, None
        except Exception as ex:
            p.unlink(missing_ok=True)
            return p, str(ex)

    def run_jobs(jobs, label):
        todo = [(p, fn) for p, fn in jobs if a.force or not p.exists()]
        print(f"{label}: {len(jobs)} planned, {len(jobs) - len(todo)} already exist (skipped), {len(todo)} to make")
        with ThreadPoolExecutor(a.workers) as ex:
            for p, err in ex.map(work, todo):
                if err:
                    failed.append((p, err))
                    print(f"FAIL {p.relative_to(root)}: {err}")

    run_jobs(build_jobs(manual, only), "manualFiles")
    copied = build_automation(manual, auto, a.force)
    print(f"automationFiles: {copied} copied from manualFiles")
    write_readmes(root, manual, auto)
    for folder in (manual, auto):
        entries = write_manifest(folder)
        total = sum(e["bytes"] for e in entries)
        print(f"{folder.name}: {len(entries)} files, {total / 1e6:.1f} MB (manifest.json written)")
    print(f"{len(failed)} failed")


if __name__ == "__main__":
    main()
