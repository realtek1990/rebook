import zipfile, re

final = '/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_final.epub'
z = zipfile.ZipFile(final)

bad_patterns = [
    r'->',
    r'UI Text',
    r'Revised structure',
    r'menu items:\*',
    r'Check .* menu items',
    r'Self-correction',
    r'I will ',
    r'Footer:',
    r'Formatting check'
]

dirty_chapters = []

for name in sorted(z.namelist()):
    if not name.endswith('.xhtml') or 'nav' in name: continue
    content = z.read(name).decode('utf-8', errors='ignore')
    text = re.sub(r'<[^>]+>', '', content)
    
    for pat in bad_patterns:
        if re.search(pat, text, re.IGNORECASE):
            dirty_chapters.append(name)
            break

print(f'Total chapters in EPUB: {len([n for n in z.namelist() if n.endswith(".xhtml")])}')
print(f'Chapters with structural/thinking garbage: {len(dirty_chapters)}')
