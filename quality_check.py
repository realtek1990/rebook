#!/usr/bin/env python3
import zipfile, re, random

final = '/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_final.epub'
z = zipfile.ZipFile(final)

sample_chapters = [
    'EPUB/ch_018.xhtml',  # From the deeply technical parts
    'EPUB/ch_043.xhtml',  # Another one
    'EPUB/ch_500.xhtml',  # Middle of the book
    'EPUB/ch_1012.xhtml', # Some random other location
    'EPUB/ch_1882.xhtml'  # Late chapter
]

print("=== SZCZEGÓŁOWA KONTROLA JAKOŚCI TŁUMACZENIA ===\n")

for name in sample_chapters:
    try:
        content = z.read(name).decode('utf-8', errors='ignore')
    except KeyError:
        continue
        
    text = re.sub(r'<[^>]+>', '', content)
    text = re.sub(r'\s+', ' ', text).strip()
    
    print(f"--- ROZDZIAŁ: {name} ---")
    
    # Just show the first 500 characters to evaluate the flow
    preview = text[:800]
    print(preview)
    print("\n")
    
    # Check for specific terminology issues
    terms = ['round-trip', 'grade', 'node', 'timeline', 'color page', 'edit page', 'render']
    found = []
    for t in terms:
        if t in text.lower():
            found.append(t)
    if found:
        print(f"⚠️ Znaleziono angielskie terminy techniczne: {', '.join(found)}\n")

