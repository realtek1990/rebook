"""ReBook — FastAPI GUI Backend."""
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
import threading
from typing import Optional
import smtplib
from email.message import EmailMessage

try:
    import webview
    HAS_WEBVIEW = True
except ImportError:
    HAS_WEBVIEW = False

import markdown as md_lib
from ebooklib import epub
from fastapi import FastAPI, File, Form, UploadFile
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import corrector

app = FastAPI(title="ReBook", version="2.0")

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# App Data Directory
WORKSPACE_DIR = Path.home() / ".rebook"
UPLOAD_DIR = WORKSPACE_DIR / "uploads"
RESULTS_DIR = WORKSPACE_DIR / "results"
CONFIG_FILE = WORKSPACE_DIR / "config.json"

for d in [UPLOAD_DIR, RESULTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Generate default config if missing
if not CONFIG_FILE.exists():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "llm_provider": "gemini",
            "api_key": "",
            "model_name": "gemini-3-flash-preview",
            "workers": 30,
            "kindle_email": "",
            "smtp_email": "",
            "smtp_pass": ""
        }, f, indent=4)

MARKER_BIN = Path(sys.prefix) / "bin" / "marker_single"

# Job storage
jobs: dict[str, dict] = {}
conversion_jobs = jobs


@app.get("/", response_class=HTMLResponse)
async def index():
    return (Path(__file__).parent / "static" / "index.html").read_text()


from pydantic import BaseModel

class ConfigData(BaseModel):
    llm_provider: str
    api_key: str
    model_name: str
    kindle_email: str
    smtp_email: str
    smtp_pass: str

@app.get("/api/config")
async def get_config():
    """Pobiera aktualną konfigurację."""
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

@app.post("/api/config")
async def save_config(config: ConfigData):
    """Zapisuje konfigurację."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config.dict(), f, indent=4)
    return {"success": True}

@app.get("/api/status")
async def api_status():
    """Check system status."""
    api_ok = corrector.is_api_available()
    models = corrector.get_available_models() if api_ok else []
    kindle_mounted = Path("/Volumes/Kindle").exists()
    return {
        "api_ok": api_ok,
        "models": models,
        "kindle": kindle_mounted,
        "marker": MARKER_BIN.exists(),
    }


@app.post("/api/convert")
async def convert(
    pdf: UploadFile = File(...),
    output_format: str = Form("epub"),
    use_llm: bool = Form(False),
    llm_model: str = Form("gpt-4o-mini"),
    use_translate: bool = Form(False),
    lang_from: str = Form(""),
    lang_to: str = Form("polski"),
):
    """Start conversion job."""
    job_id = str(uuid.uuid4())[:8]
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Save uploaded PDF
    pdf_path = job_dir / pdf.filename
    with open(pdf_path, "wb") as f:
        content = await pdf.read()
        f.write(content)
    
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "stage": "upload",
        "progress": 0,
        "total": 100,
        "message": "Plik przesłany",
        "pdf_path": str(pdf_path),
        "pdf_name": pdf.filename,
        "is_md": pdf.filename.lower().endswith(".md"),
        "is_epub": pdf.filename.lower().endswith(".epub"),
        "output_format": output_format,
        "use_llm": use_llm or use_translate,
        "llm_model": llm_model,
        "use_translate": use_translate,
        "lang_from": lang_from,
        "lang_to": lang_to,
        "output_path": None,
        "result_file": None,
        "error": None,
        "log": [],
    }
    
    # Run conversion in background
    asyncio.create_task(run_conversion(job_id))
    
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """Get job status."""
    if job_id not in jobs:
        return {"error": "Job not found"}, 404
    job = jobs[job_id]
    return {
        "id": job["id"],
        "status": job["status"],
        "stage": job["stage"],
        "progress": job["progress"],
        "total": job["total"],
        "message": job["message"],
        "error": job["error"],
        "output_format": job["output_format"],
        "has_output": job["output_path"] is not None,
        "log": job["log"][-20:],  # last 20 entries
    }


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    """SSE stream for job progress."""
    async def event_generator():
        last_msg = ""
        while True:
            if job_id not in jobs:
                yield f"data: {json.dumps({'error': 'not_found'})}\n\n"
                break
            
            job = jobs[job_id]
            msg = json.dumps({
                "status": job["status"],
                "stage": job["stage"],
                "progress": job["progress"],
                "total": job["total"],
                "message": job["message"],
                "log": job["log"][-5:],
            })
            
            if msg != last_msg:
                yield f"data: {msg}\n\n"
                last_msg = msg
            
            if job["status"] in ("done", "error"):
                yield f"data: {json.dumps({'status': job['status'], 'stage': 'finished', 'message': job.get('error') or 'Gotowe!'})}\n\n"
                break
            
            await asyncio.sleep(1)
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/jobs/{job_id}/download")
async def download_job(job_id: str):
    """Download converted file."""
    if job_id not in jobs or not jobs[job_id].get("output_path"):
        return JSONResponse({"error": "File not ready"}, status_code=404)
    
    output = Path(jobs[job_id]["output_path"])
    if not output.exists():
        return JSONResponse({"error": "File not found on disk"}, status_code=404)
    
    return FileResponse(
        output,
        filename=output.name,
        media_type="application/octet-stream",
    )


@app.get("/api/jobs/{job_id}/preview")
async def preview_job(job_id: str):
    """Get text preview of converted file."""
    if job_id not in jobs:
        return {"error": "Job not found"}
    
    job = jobs[job_id]
    md_path = job.get("markdown_path")
    if not md_path or not Path(md_path).exists():
        return {"preview": "Konwersja w toku..."}
    
    text = Path(md_path).read_text(encoding="utf-8")
    # Return first 2000 chars
    return {"preview": text[:2000]}


@app.post("/api/jobs/{job_id}/kindle")
async def send_to_kindle(job_id: str):
    """Kopie wynik na Kindle przez USB lub wysyła przez Email."""
    if job_id not in conversion_jobs:
        raise HTTPException(status_code=404, detail="Nie znaleziono zadania")
        
    job = conversion_jobs[job_id]
    if job["status"] != "done" or not job["result_file"]:
        raise HTTPException(status_code=400, detail="Konwersja nie jest zakończona")
        
    result_path = RESULTS_DIR / job["result_file"]
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="Plik wynikowy nie istnieje")
        
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
        
    # Opcja 1: Send to Kindle (Email)
    if config.get("kindle_email") and config.get("smtp_email") and config.get("smtp_pass"):
        try:
            msg = EmailMessage()
            msg['Subject'] = 'Convert'
            msg['From'] = config["smtp_email"]
            msg['To'] = config["kindle_email"]
            msg.set_content(f"Przesyłam książkę: {result_path.name}")
            
            with open(result_path, 'rb') as f:
                msg.add_attachment(f.read(), maintype='application', subtype='epub+zip', filename=result_path.name)
            
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(config["smtp_email"], config["smtp_pass"])
                server.send_message(msg)
                
            return {"success": True, "method": "email"}
        except Exception as e:
            return {"success": False, "error": f"Błąd wysyłki e-mail: {e}"}

    # Opcja 2: USB Kindle Mount
    kindle_path = Path("/Volumes/Kindle/documents")
    if not kindle_path.exists():
        return {"success": False, "error": "Kindle nie podłączony przez USB i brak konfiguracji e-mail."}
        
    try:
        shutil.copy2(result_path, kindle_path / result_path.name)
        return {"success": True, "method": "usb"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def run_conversion(job_id: str):
    """Run the full conversion pipeline."""
    job = jobs[job_id]
    
    def log(msg: str):
        txt = f"[{time.strftime('%H:%M:%S')}] {msg}"
        job["log"].append(txt)
        with open(WORKSPACE_DIR / "live_status.log", "a", encoding="utf-8") as f:
            f.write(txt + "\\n")
            
    # Od razu logujemy start zadania
    log(f"--- START JOB {job_id} ---")
    
    try:
        job["status"] = "running"
        pdf_path = Path(job["pdf_path"])
        job_dir = pdf_path.parent
        
        # === Stage 1: File Check & OCR ===
        if job.get("is_md", False):
            job["stage"] = "ocr"
            job["message"] = "Pominięto OCR (wgrano gotowy tekst Markdown)"
            job["progress"] = 100
            log("Pominięto klasyczny OCR, bo plik wejściowy to *.md ułatwiający konwersję.")
            md_path = pdf_path
            job["markdown_path"] = str(md_path)
            
        else:
            if job.get("is_epub", False):
                job["stage"] = "ocr"
                job["message"] = "Rozpakowywanie EPUB na tekst (Markdown)..."
                job["progress"] = 50
                log("Rozpoczynam ekstrakcję kodu HTML e-booka (omijając silnik Markera)...")
                
                try:
                    import ebooklib
                    import ebooklib.epub as epub_in
                    from bs4 import BeautifulSoup
                    from markdownify import markdownify as mdFile
                    
                    in_book = epub_in.read_epub(str(pdf_path))
                    extracted = []
                    for item in in_book.get_items():
                        if item.get_type() == ebooklib.ITEM_DOCUMENT:
                            html = item.get_content().decode('utf-8', errors='ignore')
                            # Usuwamy deklaracje XML i DOCTYPE zanim parser je zobaczy
                            html = re.sub(r'<\?xml[^>]*\?>', '', html)
                            html = re.sub(r'<!DOCTYPE[^>]*>', '', html, flags=re.IGNORECASE)
                            soup = BeautifulSoup(html, 'html.parser')
                            # Usuwamy komentarze HTML
                            from bs4 import Comment
                            for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
                                comment.extract()
                            raw_md = mdFile(str(soup), heading_style="ATX", escape_asterisks=False)
                            extracted.append(raw_md)
                    
                    md_text_epub = "\n\n".join(extracted)
                    md_path = job_dir / f"{pdf_path.stem}.md"
                    md_path.write_text(md_text_epub, encoding="utf-8")
                    job["markdown_path"] = str(md_path)
                    job["progress"] = 100
                    log("Wewnętrzna ekstrakcja zakończona sukcesem.")
                except ImportError:
                     raise RuntimeError("Skryptowi brakuje paczek! Odpal: pip install EbookLib beautifulsoup4 markdownify")
                     
            else:
                marker_out = job_dir / "marker_output"
                job["stage"] = "ocr"
                job["message"] = "OCR — rozpoznawanie tekstu..."
                job["progress"] = 0
                log("Uruchamiam Marker OCR z akceleracją GPU (Apple Metal - zablokowane limity RAMu)...")
            
                import os
                custom_env = os.environ.copy()
                # Aby zapobiec potężnemu 'swap thrashing' na Macu z Apple Silicon (pożeranie 14GB+ VRAM),
                # ograniczamy batch size modeli Surya OCR. Zachowujemy przez to prędkość GPU (MPS), 
                # ale zmuszamy go do przetwarzania mniejszej porcji stron naraz (dostosowane na sztywno, by zmieścić się pod 8 GB RAMu).
                custom_env["RECOGNITION_BATCH_SIZE"] = "2"
                custom_env["DETECTOR_BATCH_SIZE"] = "2"
                custom_env["LAYOUT_BATCH_SIZE"] = "2"
                custom_env["TABLE_REC_BATCH_SIZE"] = "2"
                custom_env["OCR_ERROR_BATCH_SIZE"] = "2"
                custom_env["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
                custom_env.pop("TORCH_DEVICE", None)
            
                proc = await asyncio.create_subprocess_exec(
                    str(MARKER_BIN),
                    str(pdf_path),
                    "--output_dir", str(marker_out),
                    "--output_format", "markdown",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=custom_env
                )
            
                # Monitor progress (czytanie blokowe co 64 bajty by ominąć blokadę tqdm by \r)
                buffer = ""
                while True:
                    chunk = await proc.stdout.read(64)
                    if not chunk:
                        break
                
                    text = chunk.decode("utf-8", errors="replace")
                    buffer += text
                
                    # Wyszukaj wystąpienia np. '45%' w naszym buforze
                    matches = list(re.finditer(r'(\d{1,3})%', buffer))
                    if matches:
                        pct = int(matches[-1].group(1))
                        if pct <= 100:
                            job["progress"] = pct
                        
                            last_chunks = buffer.split('\r')[-1].split('\n')[-1]
                            if "Layout" in last_chunks:
                                job["message"] = f"OCR — layout: {pct}%"
                            elif "Text" in last_chunks:
                                job["message"] = f"OCR — tekst: {pct}%"
                            elif "table" in last_chunks.lower():
                                job["message"] = f"OCR — tabele: {pct}%"
                            else:
                                job["message"] = f"OCR — {pct}%"
                
                    # Bezpieczne czyszczenie bufora (zostawiamy końcówkę do łączenia uciętych %)
                    if len(buffer) > 1024:
                        buffer = buffer[-200:]
            
                await proc.wait()
            
                if proc.returncode != 0:
                    raise RuntimeError("Marker OCR failed")
            
                # Find markdown output
                md_files = list(marker_out.rglob("*.md"))
                if not md_files:
                    raise RuntimeError("No markdown output from Marker")
            
                md_path = md_files[0]
                job["markdown_path"] = str(md_path)
                log(f"OCR zakończone: {md_path.name}")
        
        # === Stage 2: LLM Correction (optional) ===
        md_text = md_path.read_text(encoding="utf-8")
        
        if job["use_llm"]:
            job["stage"] = "correction"
            job["message"] = "Korekcja GLM API — poprawianie tekstu..."
            job["progress"] = 0
            log("Uruchamiam korekcję GLM API (mega-bloki)...")
            
            def on_progress(current, total, msg):
                job["progress"] = int(current / total * 100)
                job["total"] = 100
                job["message"] = f"Korekcja ({current}/{total}): {msg}"
                # Także wrzucamy to do fizycznego loga!
                log(f"(Postęp: {current}/{total}) -> {msg}")
            
            loop = asyncio.get_event_loop()
            md_text = await loop.run_in_executor(
                None,
                corrector.correct_markdown,
                md_text,
                job["use_translate"],
                job["lang_to"],
                job["lang_from"],
                on_progress,
            )
            
            # Save corrected markdown
            corrected_path = md_path.parent / f"{md_path.stem}_corrected.md"
            corrected_path.write_text(md_text, encoding="utf-8")
            job["markdown_path"] = str(corrected_path)
            log("Korekcja LLM zakończona")
        
        # === Stage 3: Output conversion ===
        job["stage"] = "export"
        job["progress"] = 90
        fmt = job["output_format"]
        basename = pdf_path.stem
        
        if fmt == "epub":
            job["message"] = "Tworzenie EPUB..."
            log("Konwersja MD→EPUB...")
            output_path = job_dir / f"{basename}.epub"
            
            book = epub.EpubBook()
            book.set_identifier(f'pdf-converter-{uuid.uuid4().hex[:8]}')
            book.set_title(basename)
            book.set_language('pl')
            
            if pdf_path.suffix.lower() == ".pdf":
                try:
                    import fitz
                    doc = fitz.open(str(pdf_path))
                    if len(doc) > 0:
                        page = doc.load_page(0)
                        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                        cover_data = pix.tobytes("png")
                        book.set_cover("cover.png", cover_data)
                        log("Strona tytyłowa (okładka) została wyekstrahowana z PDF.")
                except ImportError:
                    log("Ostrzeżenie: Moduł PyMuPDF nie jest zainstalowany.")
                except Exception as e:
                    log(f"Ostrzeżenie: Nie udało się pobrać okładki z PDF ({e})")
            elif pdf_path.suffix.lower() == ".epub":
                try:
                    import ebooklib
                    import ebooklib.epub as epub_in
                    in_book = epub_in.read_epub(str(pdf_path))
                    # Kopiuj WSZYSTKIE obrazy z oryginału (okładka + ilustracje)
                    img_count = 0
                    for item in in_book.get_items_of_type(ebooklib.ITEM_IMAGE):
                        if 'cover' in item.id.lower() or 'cover' in item.file_name.lower():
                            ext = Path(item.file_name).suffix or '.jpg'
                            book.set_cover(f"cover{ext}", item.get_content())
                        else:
                            # Przepnij obraz jako element EPUB
                            img_item = epub.EpubImage()
                            img_item.file_name = item.file_name
                            img_item.media_type = item.media_type
                            img_item.content = item.get_content()
                            book.add_item(img_item)
                        img_count += 1
                    log(f"Przepięto {img_count} obrazów z oryginalnego EPUB.")
                except Exception as e:
                    log(f"Ostrzeżenie: Nie udało się pobrać obrazów z EPUB ({e})")
            else:
                log("Dodawanie okładki pominięto, gdyż wejściem nie jest PDF.")
                
            create_epub(md_text, str(output_path), basename, book=book)
            
        elif fmt == "html":
            job["message"] = "Tworzenie HTML..."
            log("Konwersja MD→HTML...")
            output_path = job_dir / f"{basename}.html"
            html_content = md_lib.markdown(md_text, extensions=['tables', 'smarty'])
            full_html = f"""<!DOCTYPE html>
<html lang="pl">
<head><meta charset="utf-8"><title>{basename}</title>
<style>body{{font-family:Georgia,serif;max-width:800px;margin:2em auto;line-height:1.6;padding:0 1em}}
h1{{font-size:1.8em}}h2{{font-size:1.4em}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:.3em .5em}}</style></head>
<body>{html_content}</body></html>"""
            output_path.write_text(full_html, encoding="utf-8")
            
        else:  # markdown
            job["message"] = "Zapisywanie Markdown..."
            output_path = job_dir / f"{basename}.md"
            output_path.write_text(md_text, encoding="utf-8")
        
        job["output_path"] = str(output_path)
        job["stage"] = "done"
        job["status"] = "done"
        job["progress"] = 100
        job["message"] = f"Gotowe! → {output_path.name}"
        log(f"Gotowe: {output_path.name} ({output_path.stat().st_size // 1024} KB)")
        
    except Exception as e:
        job["status"] = "error"
        job["stage"] = "error"
        job["error"] = str(e)
        job["message"] = f"Błąd: {e}"
        log(f"BŁĄD: {e}")


def create_epub(md_text: str, output_path: str, title: str, book=None):
    """Convert markdown to EPUB using ebooklib."""
    # Dzielimy na rozdziały po nagłówkach H1 i H2
    chapters_raw = re.split(r'(?=^#{1,2}\s)', md_text, flags=re.MULTILINE)
    
    if book is None:
        book = epub.EpubBook()
        book.set_identifier(f'pdf-converter-{uuid.uuid4().hex[:8]}')
        book.set_title(title)
        book.set_language('pl')
    
    style = epub.EpubItem(
        uid="style", file_name="style/default.css",
        media_type="text/css",
        content=b"""
body { font-family: Georgia, serif; line-height: 1.7; margin: 1em; color: #222; }
h1 { font-size: 1.8em; margin-top: 2em; border-bottom: 1px solid #ccc; padding-bottom: 0.3em; }
h2 { font-size: 1.4em; margin-top: 1.5em; }
h3 { font-size: 1.2em; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
td, th { border: 1px solid #ccc; padding: 0.3em 0.5em; }
blockquote { border-left: 3px solid #ccc; margin-left: 0; padding-left: 1em; color: #555; }
p { margin: 0.5em 0; }
"""
    )
    book.add_item(style)
    
    converter = md_lib.Markdown(extensions=['tables', 'smarty'])
    spine = ['nav']
    toc = []
    
    for i, chapter_md in enumerate(chapters_raw):
        if not chapter_md.strip():
            continue
        
        title_match = re.match(r'^(#{1,3})\s+(.+)', chapter_md.strip())
        heading_level = len(title_match.group(1)) if title_match else 99
        ch_title = title_match.group(2).strip() if title_match else f"Część {i+1}"
        ch_title = re.sub(r'<[^>]+>', '', ch_title).strip() or f"Część {i+1}"
        
        converter.reset()
        html_content = converter.convert(chapter_md)
        
        ch = epub.EpubHtml(title=ch_title[:80], file_name=f'ch_{i:03d}.xhtml', lang='pl')
        ch.content = f'<html><body>{html_content}</body></html>'
        ch.add_item(style)
        
        book.add_item(ch)
        spine.append(ch)
        
        # Tylko nagłówki H1 i H2 trafiają do spisu treści (czytelny TOC)
        if heading_level <= 2:
            toc.append(ch)
    
    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine
    
    epub.write_epub(output_path, book, {})


def start_server():
    import uvicorn
    # Start FastApi quietly
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="warning")


if __name__ == "__main__":
    import threading
    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    import time
    time.sleep(1)

    if HAS_WEBVIEW:
        webview.create_window(
            "ReBook",
            "http://127.0.0.1:8787",
            width=840,
            height=900,
            min_size=(600, 700),
            text_select=True
        )
        webview.start()
    else:
        print("ReBook GUI running at http://127.0.0.1:8787")
        print("Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
