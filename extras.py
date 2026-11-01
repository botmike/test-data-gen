"""Extra qa-example files: exact-size (upload limit), corrupt, truncated and unusual images.

Imported by generate.py, which passes itself in as `g` (so the label/encode helpers are shared).
1 MB here means 1 MiB = 1,048,576 bytes (what nginx, Spring and most upload limits use).
"""
import atexit, random, shutil, struct, tempfile, threading, zlib
from pathlib import Path
from PIL import Image, ImageDraw

MB = 1024 * 1024
SIZES_MB = [1, 5, 10, 25, 100]
SIZE_VARIANTS = [("exact", 0, "exact"), ("plus_1byte", 1, "+ 1 byte"), ("minus_1byte", -1, "- 1 byte")]
SIZE_FORMATS = {"video": ["mp4", "mov"], "image": ["jpg", "png"], "audio": ["mp3", "wav"]}

CORRUPT_SOURCES = {"video": ["mp4", "mov", "avi", "mkv", "webm"], "image": ["jpg", "png", "gif", "webp"],
                   "audio": ["mp3", "wav", "flac"]}
WRONG_EXTENSION = [("png", "mp4"), ("mp4", "png"), ("jpg", "mp3"), ("mp3", "jpg"), ("mp4", "jpg")]

# images with extreme dimensions (pixel-flood / decompression-bomb tests); tiny files, huge canvas
EXTREME = {
    "png": [(1, 1), (10000, 1), (1, 10000), (30000, 1), (1, 30000), (10000, 100), (100, 10000), (30000, 30000)],
    "jpg": [(1, 1), (10000, 1), (1, 10000), (65500, 1), (1, 65500), (10000, 100), (100, 10000)],
    "gif": [(1, 1), (10000, 1), (1, 10000), (65535, 1), (1, 65535)],
    "webp": [(1, 1), (10000, 1), (1, 10000), (16383, 1), (1, 16383)],
}

_lock = threading.Lock()
_cache = {}
_tmp = []


def _tmpdir():
    if not _tmp:
        _tmp.append(Path(tempfile.mkdtemp(prefix="qa-example-src-")))
        atexit.register(shutil.rmtree, _tmp[0], ignore_errors=True)
    return _tmp[0]


def _build(g, kind, fmt, path):
    if kind == "video":
        g.make_video(path, fmt, 640, 360, 5)
    elif kind == "image":
        g.make_image(path, fmt, 640, 480)
    else:
        g.make_audio(path, fmt, 5)


def source(g, kind, fmt):
    """A small valid file of this type, built once and cached (bytes)."""
    with _lock:
        if (kind, fmt) not in _cache:
            p = _tmpdir() / f"{kind}_{fmt}.{fmt}"
            _build(g, kind, fmt, p)
            _cache[(kind, fmt)] = p.read_bytes()
        return _cache[(kind, fmt)]


# ---- exact-size padding: each returns valid file bytes of the base grown by `pad` bytes -------------

def _split(pad, biggest, smallest):
    chunks = [biggest] * (pad // biggest)
    rest = pad % biggest
    if rest:
        if rest < smallest:
            take = smallest - rest
            chunks[-1] -= take
            rest += take
        chunks.append(rest)
    return chunks


def _syncsafe(n):
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def pad_mp4(data, pad):  # also mov: a trailing 'free' atom
    if pad < 8:
        raise ValueError("pad too small")
    return data + struct.pack(">I4s", pad, b"free") + bytes(pad - 8)


def pad_jpg(data, pad):  # COM (comment) segments after the JFIF header
    at = 2
    if data[2:4] == b"\xff\xe0":
        at = 4 + struct.unpack(">H", data[4:6])[0]
    com = b"".join(b"\xff\xfe" + struct.pack(">H", c - 2) + bytes(c - 4) for c in _split(pad, 65537, 4))
    return data[:at] + com + data[at:]


def pad_png(data, pad):  # private ancillary chunks before IEND
    out = []
    for c in _split(pad, 1 << 24, 12):
        body = b"qaPd" + bytes(c - 12)
        out.append(struct.pack(">I", c - 12) + body + struct.pack(">I", zlib.crc32(body)))
    return data[:-12] + b"".join(out) + data[-12:]


def pad_mp3(data, pad):  # grow the ID3v2 tag's padding area
    if data[:3] == b"ID3":
        size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
        end = 10 + size
        return data[:6] + _syncsafe(size + pad) + data[10:end] + bytes(pad) + data[end:]
    if pad < 10:
        raise ValueError("pad too small")
    return b"ID3\x04\x00\x00" + _syncsafe(pad - 10) + bytes(pad - 10) + data


def pad_wav(data, pad):  # JUNK chunk before 'data'; RIFF chunks are even-sized, so odd totals get 1 trailing byte
    pos = 12
    while data[pos:pos + 4] != b"data":
        pos += 8 + struct.unpack("<I", data[pos + 4:pos + 8])[0] + (struct.unpack("<I", data[pos + 4:pos + 8])[0] & 1)
    even = pad - (pad & 1)
    junk = b"JUNK" + struct.pack("<I", even - 8) + bytes(even - 8)
    new = data[:pos] + junk + data[pos:]
    new = new[:4] + struct.pack("<I", len(new) - 8) + new[8:]
    return new + (b"\0" if pad & 1 else b"")


PAD = {"mp4": pad_mp4, "mov": pad_mp4, "jpg": pad_jpg, "png": pad_png, "mp3": pad_mp3, "wav": pad_wav}


def make_size_file(g, path, kind, fmt, target, caption):
    with tempfile.TemporaryDirectory() as d:
        base = Path(d) / f"base.{fmt}"
        if kind == "video":
            g.make_video(base, fmt, 640, 360, 1, caption=caption)
        elif kind == "image":
            g.make_image(base, fmt, 640, 480, extra=caption)
        else:
            g.make_audio(base, fmt, 5)
        data = base.read_bytes()
    out = PAD[fmt](data, target - len(data))
    assert len(out) == target, (len(out), target)
    path.write_bytes(out)


# ---- corrupt / truncated -----------------------------------------------------------------------------

def corrupt_header(b):
    return bytes(32) + b[32:]


def corrupt_body(b):
    n = max(512, len(b) // 100)
    s = len(b) // 2 - n // 2
    return b[:s] + random.Random(1).randbytes(n) + b[s + n:]


def truncated_half(b):
    return b[: len(b) // 2]


def truncated_header(b):
    return b[:1024]


# ---- unusual images ----------------------------------------------------------------------------------

def make_jpg_variant(g, path, kind, w, h):
    caption = {"progressive": "progressive", "cmyk": "CMYK colour",
               "exif3": "EXIF orientation 3 (180)", "exif6": "EXIF orientation 6 (90 CW)",
               "exif8": "EXIF orientation 8 (90 CCW)"}[kind]
    img = g.image_label("jpg", w, h, caption)
    if kind == "progressive":
        img.save(path, quality=25, optimize=True, progressive=True)
    elif kind == "cmyk":
        img.convert("CMYK").save(path, quality=25)
    else:
        exif = Image.Exif()
        exif[0x0112] = int(kind[4:])
        img.save(path, quality=25, exif=exif)


def make_transparent_png(g, path, w, h):
    t = max(6, min(w, h) // 14)
    img = Image.new("RGBA", (w, h), g.YELLOW + (255,))
    d = ImageDraw.Draw(img)
    d.rectangle([t, t, w - t - 1, h - t - 1], fill=(255, 255, 255, 0))
    f = g.font(h // 10)
    for i, s in enumerate([f"IMAGE PNG {w}x{h}", "transparent background"]):
        d.text(((w - d.textlength(s, font=f)) / 2, h // 2 - h // 8 + i * (h // 7)), s, font=f, fill=(0, 0, 0, 255))
    img.save(path, optimize=True)


def make_animated(g, path, fmt):
    w, h, n, fps = 320, 240, 25, 5
    base = g.label_frame(g.YELLOW, w, h, [f"IMAGE ANIMATED {fmt.upper()} {w}x{h}", "5 sec loop"])[0]
    cf = g.font(14)
    frames = []
    for i in range(n):
        fr = base.copy()
        ImageDraw.Draw(fr).text((14, h - 40), f"t={i / fps:.1f}s frame {i + 1}/{n}", font=cf, fill=g.BLACK)
        frames.append(fr)
    kw = dict(save_all=True, append_images=frames[1:], duration=1000 // fps, loop=0)
    if fmt == "webp":
        frames[0].save(path, quality=20, method=6, **kw)
    elif fmt == "gif":
        quant = [f.quantize(16) for f in frames]
        quant[0].save(path, save_all=True, append_images=quant[1:], duration=1000 // fps, loop=0, optimize=True)
    else:
        frames[0].save(path, format="PNG", **kw)


def make_extreme(g, path, fmt, w, h):
    if fmt == "png" and w * h > 100_000_000:  # decompression-bomb sized: 1-bit so it stays cheap to build
        Image.new("1", (w, h), 0).save(path, compress_level=9)
        return
    img = Image.new("RGB", (w, h), g.YELLOW)
    if fmt == "png":
        img.quantize(2).save(path, compress_level=9)
    elif fmt == "gif":
        img.quantize(2).save(path)
    elif fmt == "jpg":
        img.save(path, quality=25)
    else:
        img.save(path, quality=20)


def corrupt_jobs(g, path_for, wrong_ext_path):
    """Corrupt / truncated / empty files made from valid sources. path_for(folder, kind, name) -> Path."""
    jobs = []
    for kind, fmts in CORRUPT_SOURCES.items():
        for fmt in fmts:
            for folder, label, fn in [("Corrupt", "corrupt_header", corrupt_header),
                                      ("Corrupt", "corrupt_body", corrupt_body),
                                      ("Truncated", "truncated_50pct", truncated_half),
                                      ("Truncated", "truncated_header_only", truncated_header),
                                      ("Corrupt", "empty_0_bytes", lambda b: b"")]:
                jobs.append((path_for(folder, kind, f"{label}_{fmt}.{fmt}"),
                             lambda p, k=kind, f=fmt, fn=fn: p.write_bytes(fn(source(g, k, f)))))
    kinds = {"mp4": "video", "mov": "video", "jpg": "image", "png": "image", "mp3": "audio"}
    for src, ext in WRONG_EXTENSION:
        jobs.append((wrong_ext_path(f"{src}_content_named_{ext}.{ext}"),
                     lambda p, s=src: p.write_bytes(source(g, kinds[s], s))))
    return jobs


def extra_jobs(g, root, only):
    jobs = []
    if "sizes" in only:
        for kind, fmts in SIZE_FORMATS.items():
            for fmt in fmts:
                for mb in SIZES_MB:
                    for name, delta, text in SIZE_VARIANTS:
                        jobs.append((root / f"SizeLimitQAExamples/{kind}/{fmt}/{fmt}_{mb}MB_{name}.{fmt}",
                                     lambda p, k=kind, f=fmt, t=mb * MB + delta, c=f"{mb} MB {text}":
                                     make_size_file(g, p, k, f, t, c)))
    if "corrupt" in only:
        jobs += corrupt_jobs(g, lambda folder, kind, name: root / f"{folder}QAExamples/{kind}/{name}",
                             lambda name: root / f"CorruptQAExamples/wrong_extension/{name}")
    if "imageextras" in only:
        img = root / "ImageQAExamples"
        for kind in ["progressive", "cmyk", "exif3", "exif6", "exif8"]:
            jobs.append((img / f"jpg/jpg_{kind}_800x600.jpg", lambda p, k=kind: make_jpg_variant(g, p, k, 800, 600)))
        jobs.append((img / "png/png_transparent_800x600.png", lambda p: make_transparent_png(g, p, 800, 600)))
        for fmt in ["jpg", "png", "webp"]:
            jobs.append((img / f"{fmt}/{fmt}_4000x3000.{fmt}",
                         lambda p, f=fmt: g.make_image(p, f, 4000, 3000, extra="large photo")))
        jobs.append((img / "webp/animated/5_sec_animated_loop_webp.webp", lambda p: make_animated(g, p, "webp")))
        jobs.append((img / "png/animated/5_sec_animated_loop_apng.png", lambda p: make_animated(g, p, "apng")))
        jobs.append((img / "gif/animated/5_sec_animated_loop_gif.gif", lambda p: make_animated(g, p, "gif")))
        for fmt, sizes in EXTREME.items():
            for w, h in sizes:
                jobs.append((img / f"extreme_dimensions/{fmt}/{fmt}_{w}x{h}.{fmt}",
                             lambda p, f=fmt, w=w, h=h: make_extreme(g, p, f, w, h)))
    return jobs
