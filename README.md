# test-data-gen

Generates the **qa-example** test data set: small, clean, labelled files for testing uploads, players,
converters and parsers. Videos, images, audio, documents, spreadsheets, presentations, data files, web files,
archives, emails, blocked extensions, odd file names, exact-size files, and corrupt or truncated files.

Every video and image shows what it is (format, size, codec),
so a screenshot of any frame tells you exactly which file it came from.

## 1. Just want the files? Download them

You do not need to run any code. Download the ready-made files:

- Automation set (the smallest file of every format, for automated tests): https://qa-example.com/automation-qa-example-files
- Manual set (every format, size and duration, for manual testing): https://qa-example.com/manual-qa-example-files
- Everything: https://qa-example.com/all-qa-example-files

## 2. Generate the files yourself

### Quick start (macOS or Ubuntu/Debian)

```
git clone <this repo>
cd test-data-gen
bash setup.sh
source .venv/bin/activate
python generate.py
```

`setup.sh` checks for Python 3.10+, ffmpeg, LibreOffice and zip, installs whatever is missing
(Homebrew on macOS, apt on Ubuntu/Debian), creates `.venv` and installs the Python packages. It is safe to run again.
(`bash setup.sh` needs no file permissions. `./setup.sh` also works if the file is executable; if you get "Permission denied", run `chmod +x setup.sh` or just use `bash setup.sh`.)
On macOS you need [Homebrew](https://brew.sh) first. On Windows, use WSL (Ubuntu) and run the same commands inside it.

### Requirements (what `setup.sh` installs)

| Tool | Used for |
|---|---|
| Python 3.10 or newer | the generator (tested on 3.13) |
| ffmpeg (with libx264, libx265, libvpx-vp9, libmp3lame, libopus) | video and audio |
| LibreOffice (`soffice` on the path) | doc, xls, ppt, odt, ods, odp, rtf |
| `zip` command line | password-protected zip |
| macOS `sips` | HEIC images only |

Python packages are in `requirements.txt` (Pillow, python-pptx, pypdf, cryptography, py7zr).
Tested on macOS. If a tool is missing, the files
that need it print `FAIL` and everything else still builds, so on Linux you will get everything except HEIC.

### Run it

After `bash setup.sh`:

```
source .venv/bin/activate
python generate.py
```

If you would rather not use `setup.sh`, install the tools in the table above yourself, then:
`python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python generate.py`

The files are written to `qa-example-data/` inside this project (it is git-ignored, so nothing you build is ever committed).
A full run takes about a minute and writes about 2.7 GB, nearly all of it the 5 to 100 MB exact-size files.
To skip those and write about 40 MB:

```
python generate.py --only video,image,audio,corrupt,imageextras,documents
```

| Option | Meaning |
|---|---|
| `--root DIR` | where to write the files (default: `qa-example-data/` next to `generate.py`) |
| `--only LIST` | comma list of `video,image,audio,sizes,corrupt,imageextras,documents` (default: all) |
| `--force` | remake files that already exist (by default existing files are skipped, so it is safe to re-run) |
| `--workers N` | parallel jobs (default 3) |

The text on the files uses Arial Bold on macOS and Pillow's built-in font elsewhere (see `FONT_PATHS` in `generate.py`).

## 3. What is produced

```
qa-example-data/
  manualFiles/        everything (706 files)
  automationFiles/    the smallest file of each format, flat folders (93 files, about 0.6 MB)
  README.md
```

Each folder also has a `manifest.json` listing every file with its size, SHA-256, codec, resolution and duration.

### manualFiles (one folder per format inside each group)

| Group | Files | Contents |
|---|---|---|
| `VideoQAExamples` | 352 | mp4, m4v, mov, avi, mkv, webm, mpeg, wmv, flv, 3gp, mxf, ts. 1 and 5 sec at 7 sizes (320x240 to 1080x1920), plus 30 sec mp4 and mov. Each with and without an audio track |
| `ImageQAExamples` | 90 | jpg, png, bmp, tiff, webp, heic, avif, gif (static and animated), ico, svg, apng. Plus EXIF-rotated, progressive, CMYK and transparent images, 4000x3000 photos, and `extreme_dimensions` (up to 65535 wide or tall, and a 30000x30000 PNG) for pixel-flood tests |
| `AudioQAExamples` | 18 | mp3, wav, flac, ogg, opus, m4a, aac, aiff, wma at 1 and 5 sec |
| `DocumentQAExamples` | 21 | pdf (1, 10, 100 pages, image-only, password), docx, doc, odt, rtf, txt (encodings and line endings), md, epub |
| `SpreadsheetQAExamples` | 19 | xlsx, xls, ods, csv (BOM, semicolon, quoted fields, empty), tsv |
| `PresentationQAExamples` | 6 | pptx, ppt, odp |
| `DataQAExamples` | 11 | json, xml (valid and invalid), yaml, sql, ndjson |
| `WebQAExamples` | 5 | html, css, js |
| `ArchiveQAExamples` | 10 | zip (nested, empty, password), tar, tar.gz, gz, 7z |
| `EmailQAExamples` | 4 | eml, ics, vcf |
| `BlockedExtensionQAExamples` | 6 | exe, dll, bat, sh, php, jar, all with harmless content, for upload blocklist tests |
| `FilenameQAExamples` | 9 | spaces, unicode, long names, double extension, no extension, special characters |
| `SizeLimitQAExamples` | 90 | mp4, mov, jpg, png, mp3, wav at 1, 5, 10, 25 and 100 MB: exact, plus 1 byte, minus 1 byte |
| `CorruptQAExamples` | 41 | zeroed headers, damaged bodies, empty files, wrong extensions |
| `TruncatedQAExamples` | 24 | cut at 50 percent, or header only |

### automationFiles

Flat folders `video/`, `image/`, `audio/`, `document/`, `spreadsheet/`, `presentation/`, `data/`, `web/`, `archive/`,
`email/`, `blocked/` and `filename/`. These are copies of the smallest file of each format: 1 sec 320x240 videos,
160x120 images, 1 sec audio, and the one-page, one-sheet or three-row documents. Every format is still covered, and
most files are a few hundred bytes to a few KB.

### File names

- Video: `{secs}_sec_{format}_{videocodec}[_{audiocodec}]_{WxH}.{ext}`, e.g. `5_sec_mp4_h264_aac_1280x720.mp4` (no audio codec in the name means no audio track)
- Image: `{format}_{WxH}.{ext}`, e.g. `png_800x600.png`
- Audio: `{secs}_sec_{format}.{ext}`
- Documents and data: `{format}_{description}.{ext}`, e.g. `pdf_10_pages.pdf`, `csv_100_rows.csv`, `json_invalid.json`
- Size files: `{format}_{N}MB_exact`, `_plus_1byte`, `_minus_1byte`. 1 MB means 1 MiB (1,048,576 bytes)

### Colour coding

Videos have a thick pink border and images a thick yellow border. Documents have a blue border, spreadsheets a green
header, and presentations an orange border.

### Good to know

- The password for the password-protected pdf and zip is `qa-example`.
- Legacy `.ppt` files are about 600 KB each, because LibreOffice embeds a preview image. They are in `manualFiles` only.
- File names over 150 characters (the 255-character test file) break checkouts on Windows, so keep that in mind if you commit the output anywhere.
- The `extreme_dimensions` images are small on disk but huge as pictures. Many tools refuse to open them on purpose.

## Licence

The generator code is MIT licensed (see `LICENSE`). The files it produces are released under CC0 1.0 (public domain).
