package com.rebook.app.domain

import java.io.*
import java.util.UUID
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/**
 * Minimal EPUB 3 writer.
 * Converts markdown chapters into a valid EPUB file.
 *
 * EPUB structure:
 * ├── mimetype
 * ├── META-INF/container.xml
 * └── OEBPS/
 *     ├── content.opf
 *     ├── toc.xhtml
 *     ├── chapter_001.xhtml
 *     └── ...
 */
object EpubWriter {

    data class Chapter(val title: String, val htmlBody: String)

    /**
     * Create an EPUB file from markdown text.
     *
     * @param markdown Full markdown text
     * @param title Book title
     * @param language ISO 639-1 language code (e.g., "pl", "en")
     * @param outputFile Output file path
     */
    fun write(markdown: String, title: String, language: String, outputFile: File) {
        val chapters = splitIntoChapters(markdown)
        val bookId = UUID.randomUUID().toString()

        ZipOutputStream(BufferedOutputStream(FileOutputStream(outputFile))).use { zip ->
            // mimetype MUST be first entry, uncompressed
            val mimeEntry = ZipEntry("mimetype").apply { method = ZipEntry.STORED; size = 20; compressedSize = 20; crc = 0x2CAB616F }
            zip.putNextEntry(mimeEntry)
            zip.write("application/epub+zip".toByteArray())
            zip.closeEntry()

            // META-INF/container.xml
            addEntry(zip, "META-INF/container.xml", containerXml())

            // OEBPS/content.opf
            addEntry(zip, "OEBPS/content.opf", contentOpf(bookId, title, language, chapters))

            // OEBPS/toc.xhtml
            addEntry(zip, "OEBPS/toc.xhtml", tocXhtml(title, chapters))

            // OEBPS/style.css
            addEntry(zip, "OEBPS/style.css", stylesheet())

            // Chapters
            chapters.forEachIndexed { index, chapter ->
                val filename = "chapter_%03d.xhtml".format(index + 1)
                addEntry(zip, "OEBPS/$filename", chapterXhtml(chapter, title))
            }
        }
    }

    /**
     * Split markdown into chapters by # headings.
     */
    fun splitIntoChapters(markdown: String): List<Chapter> {
        val lines = markdown.lines()
        val chapters = mutableListOf<Chapter>()
        var currentTitle = "Introduction"
        val currentBody = StringBuilder()

        for (line in lines) {
            if (line.startsWith("# ") && currentBody.isNotEmpty()) {
                chapters.add(Chapter(currentTitle, markdownToHtml(currentBody.toString())))
                currentBody.clear()
                currentTitle = line.removePrefix("# ").trim()
            } else if (line.startsWith("# ") && currentBody.isEmpty()) {
                currentTitle = line.removePrefix("# ").trim()
            } else {
                currentBody.appendLine(line)
            }
        }
        if (currentBody.isNotEmpty()) {
            chapters.add(Chapter(currentTitle, markdownToHtml(currentBody.toString())))
        }
        if (chapters.isEmpty()) {
            chapters.add(Chapter("Content", markdownToHtml(markdown)))
        }
        return chapters
    }

    /**
     * Basic markdown → HTML converter for EPUB content.
     */
    private fun markdownToHtml(md: String): String {
        val sb = StringBuilder()
        for (line in md.lines()) {
            val trimmed = line.trim()
            when {
                trimmed.startsWith("## ") -> sb.appendLine("<h2>${escHtml(trimmed.removePrefix("## "))}</h2>")
                trimmed.startsWith("### ") -> sb.appendLine("<h3>${escHtml(trimmed.removePrefix("### "))}</h3>")
                trimmed.startsWith("> ") -> sb.appendLine("<blockquote><p>${formatInline(trimmed.removePrefix("> "))}</p></blockquote>")
                trimmed.startsWith("- ") || trimmed.startsWith("* ") -> sb.appendLine("<li>${formatInline(trimmed.substring(2))}</li>")
                trimmed == "---" -> sb.appendLine("<hr/>")
                trimmed.isBlank() -> sb.appendLine()
                else -> sb.appendLine("<p>${formatInline(trimmed)}</p>")
            }
        }
        return sb.toString()
    }

    private fun formatInline(text: String): String {
        var result = escHtml(text)
        // Bold: **text**
        result = Regex("\\*\\*(.+?)\\*\\*").replace(result) { "<strong>${it.groupValues[1]}</strong>" }
        // Italic: *text*
        result = Regex("\\*(.+?)\\*").replace(result) { "<em>${it.groupValues[1]}</em>" }
        return result
    }

    private fun escHtml(s: String): String = s
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\"", "&quot;")

    // ── XML Templates ─────────────────────────────────────────────

    private fun containerXml() = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    private fun contentOpf(id: String, title: String, lang: String, chapters: List<Chapter>) = buildString {
        appendLine("""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:$id</dc:identifier>
    <dc:title>${escHtml(title)}</dc:title>
    <dc:language>$lang</dc:language>
    <dc:creator>ReBook AI</dc:creator>
    <meta property="dcterms:modified">${java.time.Instant.now().toString().take(19)}Z</meta>
  </metadata>
  <manifest>
    <item id="style" href="style.css" media-type="text/css"/>
    <item id="toc" href="toc.xhtml" media-type="application/xhtml+xml" properties="nav"/>""")
        chapters.forEachIndexed { i, _ ->
            val fn = "chapter_%03d.xhtml".format(i + 1)
            appendLine("""    <item id="ch${i + 1}" href="$fn" media-type="application/xhtml+xml"/>""")
        }
        appendLine("""  </manifest>
  <spine>""")
        chapters.forEachIndexed { i, _ ->
            appendLine("""    <itemref idref="ch${i + 1}"/>""")
        }
        appendLine("""  </spine>
</package>""")
    }

    private fun tocXhtml(title: String, chapters: List<Chapter>) = buildString {
        appendLine("""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>${escHtml(title)}</title></head>
<body>
  <nav epub:type="toc">
    <h1>Table of Contents</h1>
    <ol>""")
        chapters.forEachIndexed { i, ch ->
            val fn = "chapter_%03d.xhtml".format(i + 1)
            appendLine("""      <li><a href="$fn">${escHtml(ch.title)}</a></li>""")
        }
        appendLine("""    </ol>
  </nav>
</body>
</html>""")
    }

    private fun chapterXhtml(chapter: Chapter, bookTitle: String) = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>${escHtml(chapter.title)}</title>
  <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
  <h1>${escHtml(chapter.title)}</h1>
  ${chapter.htmlBody}
</body>
</html>"""

    private fun stylesheet() = """
body { font-family: Georgia, serif; margin: 1em; line-height: 1.6; color: #222; }
h1 { font-size: 1.8em; margin-top: 2em; border-bottom: 1px solid #ccc; padding-bottom: 0.3em; }
h2 { font-size: 1.4em; margin-top: 1.5em; }
h3 { font-size: 1.2em; }
p { text-indent: 1.5em; margin: 0.5em 0; }
blockquote { margin: 1em 2em; font-style: italic; color: #555; border-left: 3px solid #ccc; padding-left: 1em; }
hr { border: none; border-top: 1px solid #ddd; margin: 2em 0; }
li { margin: 0.3em 0; }
"""

    private fun addEntry(zip: ZipOutputStream, path: String, content: String) {
        zip.putNextEntry(ZipEntry(path))
        zip.write(content.toByteArray(Charsets.UTF_8))
        zip.closeEntry()
    }
}
