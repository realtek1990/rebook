#!/usr/bin/env python3
import zipfile
import re
import os
import shutil

INPUT_EPUB = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_final.epub"
OUTPUT_EPUB = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_cleaned.epub"

def is_meta_paragraph(text):
    text_lower = text.lower()
    
    # Direct bad keywords
    meta_keywords = [
        "let's check the rules",
        "i will translate",
        "i'll translate",
        "self-correction",
        "the prompt",
        "formatting check",
        "final polish phrasing",
        "checking the",
        "final structure",
        "image tags",
        "the text is already",
        "no translation needed",
        "i will output",
        "wait,",
        "the user wants",
        "ocr engine",
        "translation engine",
        "input:",
        "task:",
        "observation:",
        "i will extract",
        "here is the exact text"
    ]
    
    for kw in meta_keywords:
        if kw in text_lower:
            return True
            
    # Check if the paragraph is overwhelmingly English
    words = text.split()
    if len(words) < 3:
        return False
        
    eng_words = {'the','and','or','is','in','to','for','of','a','you','can','this','with','that','on','are','as','by','from','your','will','if','not','use','be','it','an','at','but','have','has','was','were','when','there','which','each','should','would','could', 'i', 'let'}
    
    eng_count = sum(1 for w in words if w.lower().strip('.,;:!?()"') in eng_words)
    eng_pct = eng_count / len(words)
    
    # If more than 30% of the paragraph is basic English words, it's probably an artifact
    if eng_pct > 0.3 and len(words) > 5:
        return True
        
    return False

print(f"📦 Otwieranie pliku EPUB: {INPUT_EPUB}")
z_in = zipfile.ZipFile(INPUT_EPUB, "r")
z_out = zipfile.ZipFile(OUTPUT_EPUB, "w", zipfile.ZIP_DEFLATED)
cleaned_chapters = 0

for item in z_in.infolist():
    data = z_in.read(item.filename)
    if item.filename.endswith('.xhtml') and 'nav' not in item.filename:
        content = data.decode('utf-8', errors='ignore')
        
        # Parse XML paragraphs
        lines = content.split('\n')
        new_lines = []
        changed = False
        
        in_body = False
        for line in lines:
            if '<body>' in line:
                in_body = True
                new_lines.append(line)
                continue
                
            if in_body and '<p>' in line and '</p>' in line:
                # Extract text inside <p>...</p> or <hX>...</hX>
                m = re.search(r'<(p|h[1-6])>(.*?)</\1>', line)
                if m:
                    inner_text = m.group(2)
                    raw_text = re.sub(r'<[^>]+>', '', inner_text) # remove nested tags like spans for check
                    
                    if is_meta_paragraph(raw_text):
                        changed = True
                        # print(f"Removing: {raw_text[:100]}...")
                        # Skip adding this line
                        continue
            
            # Additional cleanup for plain text paragraphs without tags if they somehow exist
            # Or list items
            if in_body and '<p>•' in line:
                m = re.search(r'<p>•\s*(.*?)</p>', line)
                if m:
                    inner_text = m.group(1)
                    raw_text = re.sub(r'<[^>]+>', '', inner_text)
                    if is_meta_paragraph(raw_text):
                        changed = True
                        continue

            new_lines.append(line)
            
        if changed:
            cleaned_chapters += 1
            z_out.writestr(item, '\n'.join(new_lines).encode("utf-8"))
        else:
            z_out.writestr(item, data)
    else:
        z_out.writestr(item, data)

z_in.close()
z_out.close()

print(f"🎉 Oczyszczono EPUB! Usunięto wtrącenia z {cleaned_chapters} rozdziałów.")
print(f"Nowy plik: {OUTPUT_EPUB}")
