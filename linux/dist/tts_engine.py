"""
tts_engine.py — ReBook Audiobook Generator
Uses edge-tts (free, Microsoft Neural voices via Edge browser endpoint).
"""
from __future__ import annotations

import asyncio
import os
import re
import threading
import zipfile
from pathlib import Path
from typing import Callable

# ── Voice catalogue ──────────────────────────────────────────────────────────

VOICES: dict[str, str] = {
    "pl-PL-MarekNeural": "Marek (PL, Męski)",
    "pl-PL-ZofiaNeural": "Zofia (PL, Żeński)",
    "en-US-GuyNeural":   "Guy (EN, Male)",
    "en-US-JennyNeural": "Jenny (EN, Female)",
    "es-ES-AlvaroNeural": "Alvaro (ES, Male)",
    "es-ES-ElviraNeural": "Elvira (ES, Female)",
    "de-DE-ConradNeural": "Conrad (DE, Male)",
    "fr-FR-HenriNeural":  "Henri (FR, Male)",
}

VOICE_SAMPLE_TEXT: dict[str, str] = {
    "pl-PL-MarekNeural":  "Witaj! Jestem Marek. Twój lektor audiobooków.",
    "pl-PL-ZofiaNeural":  "Witaj! Jestem Zofia. Twój lektor audiobooków.",
    "en-US-GuyNeural":    "Hello! I'm Guy, your audiobook narrator.",
    "en-US-JennyNeural":  "Hello! I'm Jenny, your audiobook narrator.",
    "es-ES-AlvaroNeural": "¡Hola! Soy Álvaro, tu narrador de audiolibros.",
    "es-ES-ElviraNeural": "¡Hola! Soy Elvira, tu narradora de audiolibros.",
    "de-DE-ConradNeural": "Hallo! Ich bin Conrad, Ihr Hörbuch-Erzähler.",
    "fr-FR-HenriNeural":  "Bonjour! Je suis Henri, votre narrateur.",
}

# ── Chapter detection ────────────────────────────────────────────────────────

# Patterns that indicate the start of a new chapter (multiline, check each line)
_CHAPTER_PATTERNS = [
    # Markdown headings (from EPUB conversion)
    re.compile(r'^#{1,2}\s+.{1,80}', re.MULTILINE),
    # Polish
    re.compile(r'^(?:Rozdział|Rozdzial|ROZDZIAŁ|Część|CZEŚĆ|Prolog|Epilog|Wstęp|Posłowie)\s*(?:[\dIVXivx]+\.?\s*[-–]?\s*)?', re.MULTILINE | re.IGNORECASE),
    # English
    re.compile(r'^(?:Chapter|CHAPTER|Part|PART|Prologue|Epilogue|Introduction|Conclusion)\s*(?:[\dIVXivx]+\.?\s*)?', re.MULTILINE | re.IGNORECASE),
    # Spanish
    re.compile(r'^(?:Capítulo|Capitulo|CAPÍTULO|Parte)\s*(?:[\dIVXivx]+\.?\s*)?', re.MULTILINE | re.IGNORECASE),
    # German / French
    re.compile(r'^(?:Kapitel|Chapitre)\s*(?:[\dIVXivx]+\.?\s*)?', re.MULTILINE | re.IGNORECASE),
]

_MIN_CHAPTER_WORDS = 400     # Merge shorter chapters with the next
_FALLBACK_WORDS_PER_CHUNK = 5000  # When no patterns found


class Chapter:
    def __init__(self, title: str, text: str, index: int):
        self.title = title
        self.text = text
        self.index = index

    def __repr__(self):
        return f"Chapter({self.index}: '{self.title}', {len(self.text.split())} words)"


def detect_chapters(text: str) -> list[Chapter]:
    """
    Smart chapter detection with fallback chain:
    1. Markdown headings (# / ##)
    2. Language-specific regex patterns
    3. Word-count fallback (every 5000 words)
    """
    # Try markdown headings first (most reliable after EPUB conversion)
    md_splits = re.split(r'(?=^#{1,2}\s)', text, flags=re.MULTILINE)
    md_splits = [s.strip() for s in md_splits if s.strip()]

    if len(md_splits) > 1:
        return _build_chapters(md_splits, source="markdown")

    # Try language patterns
    for pattern in _CHAPTER_PATTERNS[1:]:  # skip md pattern
        positions = [m.start() for m in pattern.finditer(text)]
        if len(positions) >= 2:
            parts = _split_at_positions(text, positions)
            if len(parts) > 1:
                return _build_chapters(parts, source="pattern")

    # Fallback: split by word count
    return _split_by_words(text, _FALLBACK_WORDS_PER_CHUNK)


def _split_at_positions(text: str, positions: list[int]) -> list[str]:
    parts = []
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        parts.append(text[pos:end].strip())
    return [p for p in parts if p]


def _build_chapters(parts: list[str], source: str) -> list[Chapter]:
    chapters = []
    buffer = ""
    buffer_title = "Wstęp"

    for part in parts:
        # Extract title from first line
        first_line = part.split('\n')[0].strip()
        title = re.sub(r'^#+\s*', '', first_line)[:80] or "Rozdział"

        word_count = len(part.split())
        if word_count < _MIN_CHAPTER_WORDS and chapters:
            # Too short — merge with previous
            chapters[-1].text += "\n\n" + part
        elif buffer and len(buffer.split()) < _MIN_CHAPTER_WORDS:
            buffer += "\n\n" + part
        else:
            if buffer:
                chapters.append(Chapter(buffer_title, buffer, len(chapters)))
            buffer = part
            buffer_title = title

    if buffer:
        chapters.append(Chapter(buffer_title, buffer, len(chapters)))

    return chapters if chapters else [Chapter("Cała książka", "\n\n".join(parts), 0)]


def _split_by_words(text: str, words_per_chunk: int) -> list[Chapter]:
    words = text.split()
    chapters = []
    for i in range(0, len(words), words_per_chunk):
        chunk = " ".join(words[i:i + words_per_chunk])
        chapters.append(Chapter(f"Część {len(chapters) + 1}", chunk, len(chapters)))
    return chapters


# ── Text extraction from EPUB ────────────────────────────────────────────────

def extract_text_from_epub(epub_path: str | Path) -> tuple[str, list[Chapter]]:
    """
    Extract text from EPUB, try to use its internal TOC for chapters.
    Returns (full_text, chapters).
    """
    epub_path = Path(epub_path)
    chapters_from_toc: list[Chapter] = []
    full_parts: list[str] = []

    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            # Get all xhtml/html files in reading order (sorted by name = ch_000.xhtml etc.)
            html_files = sorted(
                [f for f in z.namelist() if f.endswith(('.xhtml', '.html')) and 'nav' not in f.lower()],
                key=lambda x: x
            )
            import re as _re
            from html.parser import HTMLParser

            class _Stripper(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.result = []
                def handle_data(self, d):
                    self.result.append(d)
                def get_text(self):
                    return ''.join(self.result)

            for idx, hf in enumerate(html_files):
                raw = z.read(hf).decode('utf-8', errors='ignore')
                # Extract title from h1/h2
                title_m = _re.search(r'<h[12][^>]*>(.*?)</h[12]>', raw, _re.IGNORECASE | _re.DOTALL)
                title_raw = title_m.group(1) if title_m else f"Część {idx + 1}"
                # Strip HTML tags from title
                title_strip = _Stripper()
                title_strip.feed(title_raw)
                title = title_strip.get_text().strip()[:80] or f"Część {idx + 1}"

                # Strip all HTML for body text
                body_m = _re.search(r'<body[^>]*>(.*?)</body>', raw, _re.IGNORECASE | _re.DOTALL)
                body_html = body_m.group(1) if body_m else raw
                # Replace block tags with newlines
                body_html = _re.sub(r'<(?:p|br|div|h[1-6])[^>]*>', '\n', body_html, flags=_re.IGNORECASE)
                stripper = _Stripper()
                stripper.feed(body_html)
                text = stripper.get_text()
                text = _re.sub(r'\n{3,}', '\n\n', text).strip()

                if text and len(text.split()) > 30:
                    full_parts.append(text)
                    chapters_from_toc.append(Chapter(title, text, idx))

    except Exception as e:
        raise RuntimeError(f"Nie można odczytać EPUB: {e}")

    if not chapters_from_toc:
        raise RuntimeError("EPUB jest pusty lub nie zawiera tekstu.")

    full_text = "\n\n".join(full_parts)

    # If EPUB has meaningful chapters (>1) return them directly
    if len(chapters_from_toc) > 1:
        return full_text, chapters_from_toc

    # Single chapter EPUB — run smart detection on full text
    return full_text, detect_chapters(full_text)


# ── Edge TTS generation ──────────────────────────────────────────────────────

def _clean_text_for_tts(text: str) -> str:
    """Remove markdown syntax and excessive whitespace for TTS."""
    # Remove markdown headings markers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove markdown bold/italic
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', text)
    # Remove markdown links [text](url)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Remove code blocks
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`[^`]+`', '', text)
    # Remove horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Clean whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


async def _generate_chapter_async(text: str, voice: str, output_path: str,
                                   max_retries: int = 2, timeout: int = 120):
    """Generate a single chapter using edge-tts with retry + timeout."""
    try:
        import edge_tts
    except ImportError:
        import subprocess, sys
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "edge-tts"],
            check=True, capture_output=True
        )
        import edge_tts

    last_err = None
    for attempt in range(max_retries + 1):
        try:
            communicate = edge_tts.Communicate(text, voice)
            await asyncio.wait_for(communicate.save(output_path), timeout=timeout)
            return  # success
        except (asyncio.TimeoutError, Exception) as e:
            last_err = e
            if attempt < max_retries:
                await asyncio.sleep(1 + attempt)  # brief backoff
    raise RuntimeError(f"edge-tts failed after {max_retries+1} attempts: {last_err}")


def generate_sample(voice: str, callback: Callable[[str | None], None]):
    """
    Generate and play the voice sample in a background thread.
    callback(None) = success and auto-play, callback(error) = failure.
    """
    sample_text = VOICE_SAMPLE_TEXT.get(voice, "Witaj!")

    def _run():
        try:
            import edge_tts, subprocess, tempfile, sys, platform
            tmp = tempfile.mktemp(suffix=".mp3")
            asyncio.run(_generate_chapter_async(sample_text, voice, tmp))
            # Cross-platform audio playback
            if platform.system() == "Darwin":
                subprocess.Popen(["afplay", tmp])
            elif platform.system() == "Windows":
                os.startfile(tmp)
            else:
                # Linux: try mpv, then aplay via ffmpeg, then xdg-open
                for cmd in (["mpv", "--no-video", tmp], ["xdg-open", tmp]):
                    try:
                        subprocess.Popen(cmd)
                        break
                    except FileNotFoundError:
                        continue
            callback(None)
        except Exception as e:
            callback(str(e))

    threading.Thread(target=_run, daemon=True).start()


def list_chapters(epub_path: str) -> list[Chapter]:
    """Return chapter list from EPUB without generating audio."""
    _full_text, chapters = extract_text_from_epub(epub_path)
    return chapters


def generate_audiobook(
    epub_path: str,
    voice: str,
    output_dir: str,
    progress_cb: Callable[[int, int, str], None] | None = None,
    selected_chapters: list[int] | None = None,
) -> list[str]:
    """
    Generate audiobook MP3s from an EPUB file (parallel, 8 concurrent).
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if progress_cb:
        progress_cb(0, 1, "Czytam EPUB…")

    _full_text, chapters = extract_text_from_epub(epub_path)
    if selected_chapters is not None:
        chapters = [c for c in chapters if c.index in selected_chapters]
    total = len(chapters)

    # Prepare chapter jobs
    jobs = []
    for i, chapter in enumerate(chapters):
        clean_text = _clean_text_for_tts(chapter.text)
        if not clean_text.strip():
            continue
        safe_title = re.sub(r'[^\w\s-]', '', chapter.title)[:50].strip()
        safe_title = re.sub(r'\s+', '_', safe_title)
        filename = f"{i + 1:02d}_{safe_title}.mp3"
        out_path = str(out_dir / filename)
        # Pre-compute chunks so we can count total work units
        chunks = _chunk_text(clean_text, max_chars=4500)
        jobs.append((i, chapter.title, clean_text, out_path, chunks))

    total_chunks = sum(len(ch[4]) for ch in jobs)

    if progress_cb:
        progress_cb(0, total_chunks,
                    f"Generuję {len(jobs)} rozdziałów ({total_chunks} fragmentów, ×8 równolegle)…")

    # Parallel generation
    generated = asyncio.run(
        _generate_all_chapters(jobs, voice, len(jobs), total_chunks, progress_cb))

    # Write M3U playlist
    m3u_path = str(out_dir / "playlist.m3u")
    with open(m3u_path, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for path in generated:
            f.write(f"#EXTINF:-1,{Path(path).stem}\n{path}\n")

    if progress_cb:
        progress_cb(total_chunks, total_chunks,
                    f"✅ Gotowe! {len(generated)} rozdziałów.")

    return generated


async def _generate_all_chapters(jobs, voice, total_chapters, total_chunks, progress_cb):
    """Generate all chapters in parallel with semaphore limit."""
    sem = asyncio.Semaphore(5)  # balance speed vs WebSocket throttling
    chunks_done = [0]  # mutable counter — tracks individual chunks
    chapters_done = [0]
    generated = []

    async def _do_one(idx, title, text, out_path, chunks):
        async with sem:
            num_chunks = len(chunks)
            if num_chunks == 1:
                if progress_cb:
                    progress_cb(chunks_done[0], total_chunks,
                                f"📖 Rozdział {chapters_done[0]+1}/{total_chapters}: {title[:35]}…")
                await _generate_chapter_async(text, voice, out_path)
                chunks_done[0] += 1
            else:
                import tempfile
                tmp_files = []
                for j, chunk in enumerate(chunks):
                    if progress_cb:
                        progress_cb(chunks_done[0], total_chunks,
                                    f"📖 Rozdział {chapters_done[0]+1}/{total_chapters}: {title[:25]}… "
                                    f"(fragment {j+1}/{num_chunks})")
                    tmp = tempfile.mktemp(suffix=".mp3")
                    await _generate_chapter_async(chunk, voice, tmp)
                    tmp_files.append(tmp)
                    chunks_done[0] += 1
                _concat_mp3(tmp_files, out_path)
                for f in tmp_files:
                    try:
                        os.remove(f)
                    except Exception:
                        pass
            chapters_done[0] += 1
            if progress_cb:
                progress_cb(chunks_done[0], total_chunks,
                            f"✅ {chapters_done[0]}/{total_chapters} rozdziałów gotowe")
            return out_path

    tasks = [_do_one(idx, title, text, out_path, chunks)
             for idx, title, text, out_path, chunks in jobs]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, str):
            generated.append(r)
    return sorted(generated)


def _chunk_text(text: str, max_chars: int = 4500) -> list[str]:
    """Split long text into sentence-boundary chunks."""
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r'(?<=[.!?…])\s+', text)
    chunks = []
    current = ""
    for s in sentences:
        if len(current) + len(s) + 1 <= max_chars:
            current = (current + " " + s).strip()
        else:
            if current:
                chunks.append(current)
            current = s
    if current:
        chunks.append(current)
    return chunks


def _concat_mp3(input_files: list[str], output_file: str):
    """Concatenate multiple MP3 files using ffmpeg or raw binary concatenation."""
    import subprocess
    try:
        # Try ffmpeg first (best quality)
        file_list = "|".join(input_files)
        subprocess.run(
            ["ffmpeg", "-y", "-i", f"concat:{file_list}", "-acodec", "copy", output_file],
            check=True, capture_output=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback: raw binary concat (works for CBR MP3)
        with open(output_file, 'wb') as out:
            for f in input_files:
                with open(f, 'rb') as inp:
                    out.write(inp.read())
