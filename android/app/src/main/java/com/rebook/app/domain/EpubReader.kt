package com.rebook.app.domain

import org.jsoup.Jsoup
import java.io.File
import java.util.zip.ZipFile

/**
 * EPUB → Markdown reader.
 * Extracts text content from EPUB files and converts to markdown.
 */
object EpubReader {

    /**
     * Read an EPUB file and extract all text as markdown.
     *
     * @param epubFile The EPUB file to read
     * @return Markdown text with chapter headings
     */
    fun read(epubFile: File): String {
        val zip = ZipFile(epubFile)
        val chapters = mutableListOf<String>()

        // Find content.opf to get reading order
        val containerEntry = zip.getEntry("META-INF/container.xml")
        val opfPath: String
        if (containerEntry != null) {
            val containerXml = zip.getInputStream(containerEntry).bufferedReader().readText()
            opfPath = Regex("""full-path\s*=\s*["']([^"']+)["']""").find(containerXml)?.groupValues?.get(1)
                ?: "OEBPS/content.opf"
        } else {
            // Fallback: try common OPF paths
            opfPath = listOf("OEBPS/content.opf", "content.opf", "OPS/content.opf")
                .firstOrNull { zip.getEntry(it) != null } ?: "OEBPS/content.opf"
        }
        val opfDir = opfPath.substringBeforeLast("/", "")

        // Parse content.opf for spine order
        val opfEntry = zip.getEntry(opfPath) ?: return "Error: Cannot find $opfPath"
        val opfXml = zip.getInputStream(opfEntry).bufferedReader().readText()

        // Extract manifest items — handle any attribute order
        val manifest = mutableMapOf<String, String>() // id -> href
        // First find all <item .../> or <item ...>...</item> tags
        Regex("""<item\s+([^>]+?)/?>""").findAll(opfXml).forEach { match ->
            val attrs = match.groupValues[1]
            val id = Regex("""id\s*=\s*"([^"]+)"""").find(attrs)?.groupValues?.get(1)
            val href = Regex("""href\s*=\s*"([^"]+)"""").find(attrs)?.groupValues?.get(1)
            if (id != null && href != null) {
                manifest[id] = href
            }
        }

        // Extract spine order
        val spineIds = Regex("""<itemref\s+[^>]*idref\s*=\s*"([^"]+)"""").findAll(opfXml).map { it.groupValues[1] }.toList()

        // If spine is empty, fall back to manifest items with html/xhtml media-type
        val orderedItems = if (spineIds.isNotEmpty()) {
            spineIds.mapNotNull { manifest[it] }
        } else {
            manifest.values.filter { it.endsWith(".xhtml") || it.endsWith(".html") || it.endsWith(".htm") }
        }

        // Read each spine item in order
        for (href in orderedItems) {
            val entryPath = if (opfDir.isNotEmpty()) "$opfDir/$href" else href
            // Try both the raw path and URL-decoded path
            val entry = zip.getEntry(entryPath)
                ?: zip.getEntry(java.net.URLDecoder.decode(entryPath, "UTF-8"))
                ?: continue

            try {
                val html = zip.getInputStream(entry).bufferedReader().readText()
                val md = htmlToMarkdown(html)
                if (md.isNotBlank()) {
                    chapters.add(md)
                }
            } catch (e: Exception) {
                // Skip unreadable entries
            }
        }

        zip.close()
        return chapters.joinToString("\n\n")
    }

    /**
     * Convert HTML to clean markdown.
     */
    private fun htmlToMarkdown(html: String): String {
        val doc = Jsoup.parse(html)
        val body = doc.body() ?: return ""
        val sb = StringBuilder()

        fun processNode(node: org.jsoup.nodes.Node) {
            when (node) {
                is org.jsoup.nodes.TextNode -> {
                    val text = node.text().trim()
                    if (text.isNotBlank()) sb.append(text)
                }
                is org.jsoup.nodes.Element -> {
                    when (node.tagName().lowercase()) {
                        "h1" -> { sb.appendLine(); sb.appendLine("# ${node.text()}"); sb.appendLine() }
                        "h2" -> { sb.appendLine(); sb.appendLine("## ${node.text()}"); sb.appendLine() }
                        "h3" -> { sb.appendLine(); sb.appendLine("### ${node.text()}"); sb.appendLine() }
                        "p" -> { sb.appendLine(); sb.appendLine(node.text()); sb.appendLine() }
                        "br" -> sb.appendLine()
                        "strong", "b" -> sb.append("**${node.text()}**")
                        "em", "i" -> sb.append("*${node.text()}*")
                        "blockquote" -> {
                            sb.appendLine()
                            node.text().lines().forEach { sb.appendLine("> $it") }
                            sb.appendLine()
                        }
                        "li" -> sb.appendLine("- ${node.text()}")
                        "div", "section", "article", "body" -> {
                            for (child in node.childNodes()) processNode(child)
                        }
                        "img" -> { /* skip images */ }
                        else -> {
                            for (child in node.childNodes()) processNode(child)
                        }
                    }
                }
            }
        }

        for (child in body.childNodes()) processNode(child)
        return sb.toString().trim()
    }
}
