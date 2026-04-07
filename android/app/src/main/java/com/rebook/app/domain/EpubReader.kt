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
        val containerXml = zip.getInputStream(containerEntry).bufferedReader().readText()
        val opfPath = Regex("full-path=\"([^\"]+)\"").find(containerXml)?.groupValues?.get(1) ?: "OEBPS/content.opf"
        val opfDir = opfPath.substringBeforeLast("/", "")

        // Parse content.opf for spine order
        val opfEntry = zip.getEntry(opfPath) ?: return "Error: Cannot find $opfPath"
        val opfXml = zip.getInputStream(opfEntry).bufferedReader().readText()

        // Extract manifest items
        val manifest = mutableMapOf<String, String>() // id -> href
        Regex("<item\\s+[^>]*id=\"([^\"]+)\"[^>]*href=\"([^\"]+)\"[^>]*/?>").findAll(opfXml).forEach {
            manifest[it.groupValues[1]] = it.groupValues[2]
        }

        // Extract spine order
        val spineIds = Regex("<itemref\\s+idref=\"([^\"]+)\"").findAll(opfXml).map { it.groupValues[1] }.toList()

        // Read each spine item in order
        for (id in spineIds) {
            val href = manifest[id] ?: continue
            val entryPath = if (opfDir.isNotEmpty()) "$opfDir/$href" else href
            val entry = zip.getEntry(entryPath) ?: continue

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
