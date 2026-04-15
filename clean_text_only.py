#!/usr/bin/env python3
"""
FINAL cleaner v4 - usuwa brudnopisy Gemmy z EPUB bez API.
"""
import zipfile, re, tempfile, shutil, os

INPUT  = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_final.epub"
OUTPUT = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_final.epub"

HAS_POLISH = re.compile(r'[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]')

META_PATS = [
    re.compile(r'Output\s+ONLY', re.I),
    re.compile(r'Output\s+Rules?', re.I),
    re.compile(r'^Rules?\s*:', re.I),
    re.compile(r'^Constraints?\s*:', re.I),
    re.compile(r'^No\s+commentary', re.I),
    re.compile(r'^No\s+translation\s+needed', re.I),
    re.compile(r'^Keep\s+Markdown\s+formatting', re.I),
    re.compile(r'^Handle\s+images', re.I),
    re.compile(r'^(Footer|Header)\s*:', re.I),
    re.compile(r'^Side\s*[Tt]ab\s*[:\'\"\[]', re.I),
    re.compile(r'^UI\s+Text\s*\d*\s*:', re.I),
    re.compile(r'^Revised\s+structure\s*:', re.I),
    re.compile(r'^Image\s+(content|tags?|area|Caption|Labels?)\s*[:*]', re.I),
    re.compile(r'^Self-correction', re.I),
    re.compile(r'^Formatting\s+check\s*:', re.I),
    re.compile(r'^Final\s+Polish\s+phrasing\s*:', re.I),
    re.compile(r'^Final\s+structure\s*:', re.I),
    re.compile(r'^Final\s+check\s+(on\s+)?rules?', re.I),
    re.compile(r'^Final\s+check\s+(on\s+)?translation', re.I),
    re.compile(r'^Translation\s+notes?\s*:', re.I),
    re.compile(r'^(Source|Target)\s+language\s*:', re.I),
    re.compile(r'^(Heading|Section|Paragraph|Bullet|Step|Box|Table|Text\s+block|Caption|Top\s+(image|box))\s*\d*\s*:', re.I),
    re.compile(r'^\*(Heading|Section|Paragraph|Bullet|Step|Box|Main|Sub|Top|Footer|Header|Side|Image|Text)', re.I),
    re.compile(r'^I\s+will\s+(translate|extract|output|now|use|keep|place|render|list|assume)', re.I),
    re.compile(r"^I'll\s+(translate|extract|output|place|use|keep|now|render|list|assume)", re.I),
    re.compile(r"^Let'?s\s+(check|translate|now|start|refine|look|organize|just|see)", re.I),
    re.compile(r'^The\s+text\s+is\s+already', re.I),
    re.compile(r'^Input\s*:', re.I),
    re.compile(r'^Task\s*:', re.I),
    re.compile(r'^Observation\s*:', re.I),
    re.compile(r'^Check\s+".+"\s+menu\s+items?', re.I),
    re.compile(r'^Checking\s+the\s+["\']', re.I),
    re.compile(r'^Check\s+formatting\s*:', re.I),
    re.compile(r'^Check\s+against\s+rules?', re.I),
    re.compile(r'^Actually,\s+(looking|the\s+(text|page|image))', re.I),
    re.compile(r'^(Hmm|Wait),?\s', re.I),
    re.compile(r'^Looking\s+at\s+the\s+(rules?|constraints?|image|page)', re.I),
    re.compile(r'^Checking\s+(against|the)\s+rules?', re.I),
    re.compile(r'^The\s+(page|image)\s+(shows?|contains?|has)', re.I),
    re.compile(r'^This\s+(page|image)\s+(shows?|contains?|has|appears?)', re.I),
]

MAPPING_PAT = re.compile(r'^(.+?)\s*(?:->|→|&gt;|-&gt;)\s*(.+)$')

def strip_prefix(line):
    return re.sub(r'^[\*\•\-\s]+', '', line).strip()

def is_meta(line):
    s = strip_prefix(line.strip())
    if not s:
        return False
    for p in META_PATS:
        if p.match(s):
            return True
    return False

def clean_lines(text):
    result = []
    for raw in text.split('\n'):
        line = raw.strip()
        if not line:
            result.append('')
            continue
        if is_meta(line):
            continue
        m = MAPPING_PAT.match(strip_prefix(line))
        if m:
            pol = m.group(2).strip()
            eng = m.group(1).strip()
            if HAS_POLISH.search(pol):
                result.append(pol)
            elif HAS_POLISH.search(eng):
                result.append(eng)
            continue
        result.append(line)
    return '\n'.join(result).strip()

def clean_xhtml(content):
    changed = [False]

    def replace_tag(m):
        tag = m.group(1)
        inner = m.group(2)
        plain = re.sub(r'<[^>]+>', ' ', inner)
        plain = re.sub(r'&gt;', '>', plain)
        plain = re.sub(r'&lt;', '<', plain)
        plain = re.sub(r'&amp;', '&', plain)
        plain = plain.strip()
        cleaned = clean_lines(plain)
        if not cleaned:
            changed[0] = True
            return ''
        if cleaned == plain:
            return m.group(0)
        changed[0] = True
        safe = cleaned.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return f'<{tag}>{safe}</{tag}>'

    out = re.sub(r'<(p|li|h[1-6])\b[^>]*>(.*?)</\1>', replace_tag, content, flags=re.DOTALL)
    out = re.sub(r'<(p|li)\b[^>]*>\s*</\1>', '', out)
    out = re.sub(r'\n{3,}', '\n\n', out)
    return out, changed[0]

print(f"🔨 Czyszczenie (v4): {INPUT}")
z_in = zipfile.ZipFile(INPUT, "r")
fd, tmp = tempfile.mkstemp(suffix='.epub')
os.close(fd)
z_out = zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED)

cleaned_count = total = 0
for item in z_in.infolist():
    data = z_in.read(item.filename)
    if item.filename.endswith('.xhtml') and 'nav' not in item.filename:
        total += 1
        content = data.decode('utf-8', errors='ignore')
        new_content, changed = clean_xhtml(content)
        if changed:
            cleaned_count += 1
            data = new_content.encode('utf-8')
    z_out.writestr(item, data)

z_in.close()
z_out.close()
shutil.move(tmp, OUTPUT)
print(f"✅ Oczyszczono {cleaned_count}/{total} rozdziałów → {OUTPUT}")
