package com.rebook.app.ui

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import com.rebook.app.R
import com.rebook.app.domain.Converter
import com.rebook.app.domain.TtsEngine
import com.rebook.app.ui.theme.*
import java.io.File

val LANGUAGES = listOf(
    "polski", "angielski", "niemiecki", "francuski", "hiszpański",
    "portugalski", "włoski", "niderlandzki", "czeski", "słowacki",
    "ukraiński", "rosyjski", "węgierski", "rumuński", "chorwacki",
    "serbski", "turecki", "szwedzki", "norweski", "duński", "fiński",
    "chiński", "japoński", "wietnamski", "tajski", "arabski", "perski"
)

// ════════════════════════════════════════════════════════════════════════════
// Main Screen
// ════════════════════════════════════════════════════════════════════════════

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    viewModel: ConversionViewModel,
    onOpenSettings: () -> Unit,
) {
    val state by viewModel.state.collectAsState()
    val context = LocalContext.current

    // ── File pickers ─────────────────────────────────────────────────────
    val filePicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        uri?.let {
            context.contentResolver.takePersistableUriPermission(it, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            val cursor = context.contentResolver.query(it, null, null, null, null)
            cursor?.use { c ->
                c.moveToFirst()
                val nameIdx = c.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
                val sizeIdx = c.getColumnIndex(android.provider.OpenableColumns.SIZE)
                val name = if (nameIdx >= 0) c.getString(nameIdx) else "file"
                val size = if (sizeIdx >= 0) c.getLong(sizeIdx) else 0L
                viewModel.setFile(it, name, size)
            }
        }
    }

    val saveLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/octet-stream")
    ) { destUri: Uri? ->
        destUri?.let { uri ->
            state.outputPath?.let { path ->
                try {
                    val srcFile = File(path)
                    context.contentResolver.openOutputStream(uri)?.use { out ->
                        srcFile.inputStream().use { inp -> inp.copyTo(out) }
                    }
                    Toast.makeText(context, context.getString(R.string.saved_btn), Toast.LENGTH_SHORT).show()
                } catch (e: Exception) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    val epubPickerForAudiobook = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        uri?.let {
            context.contentResolver.takePersistableUriPermission(it, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            val cursor = context.contentResolver.query(it, null, null, null, null)
            val name = cursor?.use { c ->
                c.moveToFirst()
                val idx = c.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
                if (idx >= 0) c.getString(idx) else "plik.epub"
            } ?: "plik.epub"
            viewModel.setAudiobookEpub(it, name)
        }
    }

    // ── Expand state for cards ───────────────────────────────────────────
    var expandConvert  by remember { mutableStateOf(true) }
    var expandPdfTrans by remember { mutableStateOf(false) }
    var expandAudiobook by remember { mutableStateOf(false) }

    // ── About dialog ─────────────────────────────────────────────────────
    var showAbout by remember { mutableStateOf(false) }
    if (showAbout) {
        AlertDialog(
            onDismissRequest = { showAbout = false },
            title = { Text(stringResource(R.string.about_title)) },
            text = {
                Column {
                    Text(
                        stringResource(R.string.about_version, "3.15.0"),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Spacer(Modifier.height(8.dp))
                    Text(stringResource(R.string.about_body))
                }
            },
            confirmButton = { TextButton(onClick = { showAbout = false }) { Text("OK") } },
        )
    }

    // ── Chapter selector dialog ──────────────────────────────────────────
    if (state.showChapterSelector && state.audiobookChapters.isNotEmpty()) {
        ChapterSelectorDialog(state, viewModel)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            "ReBook",
                            style = MaterialTheme.typography.headlineMedium.copy(
                                fontWeight = FontWeight.ExtraBold,
                            ),
                            color = RbPrimary,
                        )
                        Spacer(Modifier.width(8.dp))
                        Surface(
                            shape = RoundedCornerShape(6.dp),
                            color = RbPrimary.copy(alpha = 0.15f),
                        ) {
                            Text(
                                "v3.15",
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                style = MaterialTheme.typography.labelSmall,
                                color = RbPrimary,
                            )
                        }
                    }
                },
                actions = {
                    IconButton(onClick = { showAbout = true }) {
                        Icon(Icons.Default.Info, "About", tint = RbOnSurface2)
                    }
                    IconButton(onClick = onOpenSettings) {
                        Icon(Icons.Default.Settings, "Settings", tint = RbOnSurface2)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Color.Transparent,
                ),
            )
        },
        containerColor = RbBackground,
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Spacer(Modifier.height(4.dp))

            // ── File Selection ──────────────────────────────────────────
            AnimatedVisibility(visible = state.selectedFileUri == null) {
                StyledDropZone(onClick = {
                    filePicker.launch(arrayOf("application/pdf", "application/epub+zip", "text/markdown"))
                })
            }
            AnimatedVisibility(visible = state.selectedFileUri != null) {
                StyledFileBadge(
                    name = state.selectedFileName,
                    size = state.selectedFileSize,
                    onRemove = { viewModel.removeFile() },
                )
            }

            // ══════════════════════════════════════════════════════════════
            // Card 1 — Konwertuj e-book
            // ══════════════════════════════════════════════════════════════
            ActionCard(
                icon = Icons.Default.AutoFixHigh,
                title = "Konwertuj e-book",
                subtitle = "PDF/EPUB → EPUB/MD/HTML",
                accentColor = RbPrimary,
                expanded = expandConvert,
                onToggle = { expandConvert = !expandConvert },
            ) {
                // Format selector chips
                Text("Format wyjściowy", style = MaterialTheme.typography.labelMedium, color = RbOnSurface2)
                Spacer(Modifier.height(4.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Converter.OutputFormat.entries.filter { it != Converter.OutputFormat.PDF }.forEach { fmt ->
                        FilterChip(
                            selected = state.outputFormat == fmt,
                            onClick = { viewModel.setOutputFormat(fmt) },
                            label = { Text(fmt.name) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = RbPrimary.copy(alpha = 0.2f),
                                selectedLabelColor = RbPrimary,
                            ),
                        )
                    }
                }

                Spacer(Modifier.height(8.dp))

                // AI correction toggle
                ToggleRow(
                    label = "🤖 Korekta AI",
                    checked = state.useAi,
                    onCheckedChange = { viewModel.setUseAi(it) },
                )

                // Page range (PDF only)
                AnimatedVisibility(visible = state.isPdf) {
                    Row(
                        modifier = Modifier.padding(top = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Text("📄", fontSize = 14.sp)
                        OutlinedTextField(
                            value = state.pageStart,
                            onValueChange = { viewModel.setPageStart(it.filter { c -> c.isDigit() }) },
                            label = { Text("Od") },
                            modifier = Modifier.width(72.dp),
                            singleLine = true,
                            textStyle = MaterialTheme.typography.bodySmall,
                        )
                        Text("–", color = RbOnSurface2)
                        OutlinedTextField(
                            value = state.pageEnd,
                            onValueChange = { viewModel.setPageEnd(it.filter { c -> c.isDigit() }) },
                            label = { Text("Do") },
                            modifier = Modifier.width(72.dp),
                            singleLine = true,
                            textStyle = MaterialTheme.typography.bodySmall,
                        )
                        if (state.totalPageCount > 0) {
                            Text("z ${state.totalPageCount}", style = MaterialTheme.typography.labelSmall, color = RbOnSurface3)
                        }
                    }
                }

                // Translation toggle
                ToggleRow(
                    label = "🌐 Tłumaczenie",
                    checked = state.translate,
                    onCheckedChange = { viewModel.setTranslate(it) },
                )

                AnimatedVisibility(visible = state.translate) {
                    Column(Modifier.padding(start = 8.dp, top = 4.dp)) {
                        LanguageDropdown(
                            label = stringResource(R.string.lang_from_label),
                            value = state.langFrom,
                            onValueChange = { viewModel.setLangFrom(it) },
                        )
                        Spacer(Modifier.height(4.dp))
                        LanguageDropdown(
                            label = stringResource(R.string.lang_to_label),
                            value = state.langTo,
                            onValueChange = { viewModel.setLangTo(it) },
                        )
                        Spacer(Modifier.height(4.dp))
                        ToggleRow("🖼 Tłumacz obrazki", state.translateImages) { viewModel.setTranslateImages(it) }
                        ToggleRow("✅ Weryfikacja", state.verify) { viewModel.setVerify(it) }
                    }
                }

                Spacer(Modifier.height(12.dp))

                // ── Convert button ──
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        onClick = { viewModel.startConversion() },
                        enabled = state.selectedFileUri != null && !state.isConverting,
                        modifier = Modifier.weight(1f).height(48.dp),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = RbPrimary),
                    ) {
                        Icon(Icons.Default.PlayArrow, null, Modifier.size(20.dp))
                        Spacer(Modifier.width(8.dp))
                        Text(
                            if (state.isConverting) stringResource(R.string.converting_btn)
                            else stringResource(R.string.convert_btn),
                            fontWeight = FontWeight.Bold,
                        )
                    }
                    AnimatedVisibility(visible = state.isConverting) {
                        FilledTonalButton(
                            onClick = { viewModel.stopConversion() },
                            modifier = Modifier.height(48.dp),
                            shape = RoundedCornerShape(12.dp),
                            colors = ButtonDefaults.filledTonalButtonColors(containerColor = RbErrorContainer),
                        ) { Text("⛔ Stop") }
                    }
                }
            }

            // ── Progress section ────────────────────────────────────────
            AnimatedVisibility(visible = state.isConverting || state.progressPercent > 0f) {
                GlassCard {
                    LinearProgressIndicator(
                        progress = { state.progressPercent },
                        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(4.dp)),
                        color = RbPrimary,
                        trackColor = RbSurfaceVariant,
                    )
                    Spacer(Modifier.height(6.dp))
                    Text(state.progressMessage, style = MaterialTheme.typography.bodySmall, color = RbOnSurface2)
                }
            }

            // ── Log ─────────────────────────────────────────────────────
            if (state.logMessages.isNotEmpty() && state.isConverting) {
                GlassCard {
                    Column(Modifier.heightIn(max = 120.dp).verticalScroll(rememberScrollState())) {
                        state.logMessages.takeLast(15).forEach { msg ->
                            Text(msg, style = MaterialTheme.typography.bodySmall.copy(
                                fontFamily = FontFamily.Monospace, fontSize = 10.sp,
                                color = RbOnSurface3,
                            ))
                        }
                    }
                }
            }

            // ── Result ──────────────────────────────────────────────────
            AnimatedVisibility(visible = state.outputPath != null) {
                ResultCard(state, saveLauncher, context)
            }

            // ══════════════════════════════════════════════════════════════
            // Card 2 — Przetłumacz PDF
            // ══════════════════════════════════════════════════════════════
            ActionCard(
                icon = Icons.Default.Translate,
                title = "Przetłumacz PDF",
                subtitle = "Zachowuje layout i formatowanie",
                accentColor = RbSecondary,
                expanded = expandPdfTrans,
                onToggle = { expandPdfTrans = !expandPdfTrans },
                badge = "NOWE",
            ) {
                Text(
                    "Tłumaczenie z zachowaniem oryginalnego układu strony.",
                    style = MaterialTheme.typography.bodySmall,
                    color = RbOnSurface2,
                )
                Spacer(Modifier.height(8.dp))
                LanguageDropdown(
                    label = stringResource(R.string.lang_from_label),
                    value = state.langFrom,
                    onValueChange = { viewModel.setLangFrom(it) },
                )
                Spacer(Modifier.height(4.dp))
                LanguageDropdown(
                    label = stringResource(R.string.lang_to_label),
                    value = state.langTo,
                    onValueChange = { viewModel.setLangTo(it) },
                )
                Spacer(Modifier.height(12.dp))
                Button(
                    onClick = {
                        viewModel.setTranslatePdf(true)
                        viewModel.startConversion()
                    },
                    enabled = state.selectedFileUri != null && !state.isConverting && state.isPdf,
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = RbSecondary),
                ) {
                    Icon(Icons.Default.Translate, null, Modifier.size(20.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("Przetłumacz PDF", fontWeight = FontWeight.Bold, color = RbOnSecondary)
                }
                if (!state.isPdf && state.selectedFileUri != null) {
                    Text(
                        "⚠️ Wymaga pliku PDF",
                        style = MaterialTheme.typography.labelSmall,
                        color = RbTertiary,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
            }

            // ══════════════════════════════════════════════════════════════
            // Card 3 — Audiobook
            // ══════════════════════════════════════════════════════════════
            ActionCard(
                icon = Icons.Default.Headphones,
                title = "Audiobook",
                subtitle = "EPUB → MP3 (Edge TTS, za darmo)",
                accentColor = RbTertiary,
                expanded = expandAudiobook,
                onToggle = { expandAudiobook = !expandAudiobook },
            ) {
                // EPUB source
                val epubLabel = when {
                    state.audiobookEpubUri != null -> state.audiobookEpubName
                    state.outputPath?.endsWith(".epub") == true -> File(state.outputPath!!).name
                    state.selectedFileName.endsWith(".epub", ignoreCase = true) -> state.selectedFileName
                    else -> null
                }
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        if (epubLabel != null) "📖 $epubLabel" else "Brak pliku EPUB",
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.weight(1f),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        color = if (epubLabel != null) RbOnSurface else RbOnSurface3,
                    )
                    OutlinedButton(
                        onClick = { epubPickerForAudiobook.launch(arrayOf("application/epub+zip")) },
                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                    ) {
                        Icon(Icons.Default.FolderOpen, null, Modifier.size(14.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Wybierz", style = MaterialTheme.typography.labelSmall)
                    }
                }

                Spacer(Modifier.height(8.dp))

                // Voice selector — dynamic per language
                val currentVoices = remember(state.langTo) { TtsEngine.voicesFor(state.langTo) }
                val voiceKeys = currentVoices.keys.toList()
                val voiceLabels = currentVoices.values.toList()

                LaunchedEffect(state.langTo) {
                    val firstKey = voiceKeys.firstOrNull()
                    if (firstKey != null && state.ttsVoice !in currentVoices) {
                        viewModel.setTtsVoice(firstKey)
                    }
                }

                Text("🎙 Głos lektora", style = MaterialTheme.typography.labelMedium, color = RbOnSurface2)
                Spacer(Modifier.height(4.dp))
                Row(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    voiceKeys.forEachIndexed { i, key ->
                        FilterChip(
                            selected = state.ttsVoice == key,
                            onClick = { viewModel.setTtsVoice(key) },
                            label = { Text(voiceLabels[i], style = MaterialTheme.typography.labelSmall) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = RbTertiary.copy(alpha = 0.2f),
                                selectedLabelColor = RbTertiary,
                            ),
                        )
                    }
                    FilledTonalButton(
                        onClick = { viewModel.playSample() },
                        enabled = !state.isSamplePlaying,
                        contentPadding = PaddingValues(horizontal = 10.dp),
                        modifier = Modifier.height(32.dp),
                    ) {
                        if (state.isSamplePlaying) {
                            CircularProgressIndicator(Modifier.size(14.dp), strokeWidth = 2.dp, color = RbTertiary)
                        } else {
                            Icon(Icons.Default.PlayArrow, null, Modifier.size(16.dp))
                        }
                    }
                }

                // Progress/error
                if (state.audiobookProgress.isNotBlank()) {
                    Text(state.audiobookProgress, style = MaterialTheme.typography.bodySmall, color = RbOnSurface2, modifier = Modifier.padding(top = 4.dp))
                }
                if (state.audiobookError != null) {
                    Text("❌ ${state.audiobookError}", style = MaterialTheme.typography.bodySmall, color = RbError, modifier = Modifier.padding(top = 4.dp))
                }
                if (state.isGeneratingAudiobook || state.audiobookProgressPercent == 1f) {
                    LinearProgressIndicator(
                        progress = { if (state.audiobookProgressPercent < 0f) 0f else state.audiobookProgressPercent },
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp).clip(RoundedCornerShape(4.dp)),
                        color = RbTertiary,
                        trackColor = RbSurfaceVariant,
                    )
                }

                Spacer(Modifier.height(12.dp))

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (state.isGeneratingAudiobook) {
                        Button(
                            onClick = { viewModel.cancelAudiobook() },
                            modifier = Modifier.weight(1f).height(44.dp),
                            shape = RoundedCornerShape(12.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = RbError),
                        ) {
                            Icon(Icons.Default.Stop, null, Modifier.size(18.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("Zatrzymaj")
                        }
                    } else {
                        Button(
                            onClick = { viewModel.startAudiobook() },
                            modifier = Modifier.weight(1f).height(44.dp),
                            shape = RoundedCornerShape(12.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = RbTertiary),
                        ) {
                            Text("🎧 Generuj audiobook", fontWeight = FontWeight.Bold, color = RbOnPrimary)
                        }
                    }
                    if (state.audiobookOutputDir != null) {
                        FilledTonalButton(
                            onClick = {
                                val dir = File(state.audiobookOutputDir!!)
                                Toast.makeText(context, "📂 ${dir.absolutePath}", Toast.LENGTH_LONG).show()
                            },
                            modifier = Modifier.height(44.dp),
                        ) {
                            Icon(Icons.Default.FolderOpen, null, Modifier.size(18.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Otwórz")
                        }
                    }
                }
            }

            // ── Pipeline: auto-audiobook toggle ─────────────────────────
            GlassCard {
                ToggleRow(
                    label = "🔗 Auto-audiobook po konwersji",
                    checked = state.pipelineAutoAudiobook,
                    onCheckedChange = { viewModel.setPipelineAutoAudiobook(it) },
                )
            }

            // ── Error ───────────────────────────────────────────────────
            AnimatedVisibility(visible = state.error != null) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = RbErrorContainer),
                    shape = RoundedCornerShape(12.dp),
                ) {
                    Text(
                        "❌ ${state.error}",
                        modifier = Modifier.padding(16.dp),
                        color = RbOnErrorContainer,
                    )
                }
            }

            Spacer(Modifier.height(32.dp))
        }
    }
}

// ════════════════════════════════════════════════════════════════════════════
// Reusable Composables
// ════════════════════════════════════════════════════════════════════════════

/** Expandable action card with accent-colored left border and icon header. */
@Composable
private fun ActionCard(
    icon: ImageVector,
    title: String,
    subtitle: String,
    accentColor: Color,
    expanded: Boolean,
    onToggle: () -> Unit,
    badge: String? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = RbCard),
    ) {
        // Accent top edge
        Box(
            Modifier
                .fillMaxWidth()
                .height(3.dp)
                .background(
                    Brush.horizontalGradient(
                        listOf(accentColor, accentColor.copy(alpha = 0.3f))
                    )
                )
        )

        Column(Modifier.padding(16.dp)) {
            // Header row — always visible, clickable to expand/collapse
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(onClick = onToggle),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Surface(
                    shape = RoundedCornerShape(10.dp),
                    color = accentColor.copy(alpha = 0.15f),
                    modifier = Modifier.size(40.dp),
                ) {
                    Box(contentAlignment = Alignment.Center, modifier = Modifier.fillMaxSize()) {
                        Icon(icon, null, tint = accentColor, modifier = Modifier.size(22.dp))
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(title, style = MaterialTheme.typography.titleMedium, color = RbOnSurface)
                        if (badge != null) {
                            Spacer(Modifier.width(8.dp))
                            Surface(
                                shape = RoundedCornerShape(4.dp),
                                color = accentColor.copy(alpha = 0.2f),
                            ) {
                                Text(
                                    badge,
                                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 1.dp),
                                    style = MaterialTheme.typography.labelSmall.copy(fontSize = 9.sp),
                                    color = accentColor,
                                    fontWeight = FontWeight.Bold,
                                )
                            }
                        }
                    }
                    Text(subtitle, style = MaterialTheme.typography.bodySmall, color = RbOnSurface3)
                }
                Icon(
                    if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                    contentDescription = null,
                    tint = RbOnSurface3,
                )
            }

            // Expandable content
            AnimatedVisibility(
                visible = expanded,
                enter = fadeIn() + expandVertically(),
                exit = fadeOut() + shrinkVertically(),
            ) {
                Column(Modifier.padding(top = 12.dp)) {
                    content()
                }
            }
        }
    }
}

/** Glass-effect surface card. */
@Composable
private fun GlassCard(content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = RbSurfaceVariant.copy(alpha = 0.5f)),
    ) {
        Column(Modifier.padding(12.dp)) { content() }
    }
}

/** Toggle row with label and switch. */
@Composable
private fun ToggleRow(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f), color = RbOnSurface)
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange,
            colors = SwitchDefaults.colors(
                checkedThumbColor = RbPrimary,
                checkedTrackColor = RbPrimary.copy(alpha = 0.3f),
            ),
        )
    }
}

/** Styled drop zone for file selection. */
@Composable
private fun StyledDropZone(onClick: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .height(130.dp)
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = RbCard),
        border = CardDefaults.outlinedCardBorder(),
    ) {
        Column(
            modifier = Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = RbPrimary.copy(alpha = 0.1f),
                modifier = Modifier.size(48.dp),
            ) {
                Box(contentAlignment = Alignment.Center, modifier = Modifier.fillMaxSize()) {
                    Icon(Icons.Default.FileOpen, null, Modifier.size(28.dp), tint = RbPrimary)
                }
            }
            Spacer(Modifier.height(10.dp))
            Text("Wybierz plik", style = MaterialTheme.typography.titleMedium, color = RbOnSurface)
            Text(
                "PDF • EPUB • Markdown",
                style = MaterialTheme.typography.bodySmall,
                color = RbOnSurface3,
            )
        }
    }
}

/** File badge showing selected file info. */
@Composable
private fun StyledFileBadge(name: String, size: String, onRemove: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = RbCard),
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                shape = RoundedCornerShape(8.dp),
                color = RbPrimary.copy(alpha = 0.12f),
                modifier = Modifier.size(36.dp),
            ) {
                Box(contentAlignment = Alignment.Center, modifier = Modifier.fillMaxSize()) {
                    Icon(Icons.Default.Description, null, Modifier.size(20.dp), tint = RbPrimary)
                }
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(name, style = MaterialTheme.typography.bodyLarge, maxLines = 1, overflow = TextOverflow.Ellipsis, color = RbOnSurface)
                Text(size, style = MaterialTheme.typography.bodySmall, color = RbOnSurface3)
            }
            IconButton(onClick = onRemove) {
                Icon(Icons.Default.Close, stringResource(R.string.remove_btn), tint = RbOnSurface3)
            }
        }
    }
}

/** Result card with save/share/open actions. */
@Composable
private fun ResultCard(
    state: ConversionState,
    saveLauncher: androidx.activity.result.ActivityResultLauncher<String>,
    context: android.content.Context,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = RbPrimaryContainer),
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(Modifier.padding(16.dp)) {
            Text(
                "✅ ${stringResource(R.string.conversion_done)}",
                style = MaterialTheme.typography.titleMedium,
                color = RbOnPrimaryContainer,
            )
            state.outputPath?.let { path ->
                Text(File(path).name, style = MaterialTheme.typography.bodySmall, color = RbOnPrimaryContainer.copy(alpha = 0.7f))
            }
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilledTonalButton(onClick = {
                    state.outputPath?.let { path -> saveLauncher.launch(File(path).name) }
                }) {
                    Icon(Icons.Default.Save, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(4.dp))
                    Text(stringResource(R.string.save_btn))
                }
                FilledTonalButton(onClick = {
                    state.outputPath?.let { path ->
                        val file = File(path)
                        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
                        val intent = Intent(Intent.ACTION_SEND).apply {
                            type = when (file.extension) { "epub" -> "application/epub+zip"; "html" -> "text/html"; else -> "text/markdown" }
                            putExtra(Intent.EXTRA_STREAM, uri)
                            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        }
                        context.startActivity(Intent.createChooser(intent, "Share"))
                    }
                }) {
                    Icon(Icons.Default.Share, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(4.dp))
                    Text(stringResource(R.string.share_btn))
                }
            }
        }
    }
}

/** Chapter selector dialog for audiobook generation. */
@Composable
private fun ChapterSelectorDialog(state: ConversionState, viewModel: ConversionViewModel) {
    AlertDialog(
        onDismissRequest = { viewModel.dismissChapterSelector() },
        title = { Text("📋 Wybierz rozdziały") },
        text = {
            Column {
                Text(
                    "Znaleziono ${state.audiobookChapters.size} rozdziałów.",
                    style = MaterialTheme.typography.bodySmall,
                )
                Spacer(Modifier.height(8.dp))

                val allSelected = state.selectedChapterIndices.size == state.audiobookChapters.size
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.clickable {
                        if (allSelected) viewModel.setSelectedChapters(emptySet())
                        else viewModel.setSelectedChapters(state.audiobookChapters.map { it.index }.toSet())
                    }
                ) {
                    Checkbox(checked = allSelected, onCheckedChange = null)
                    Text("Zaznacz wszystkie", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold)
                }

                HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

                Column(
                    modifier = Modifier.heightIn(max = 350.dp).verticalScroll(rememberScrollState())
                ) {
                    state.audiobookChapters.forEach { ch ->
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    val newSet = state.selectedChapterIndices.toMutableSet()
                                    if (ch.index in newSet) newSet.remove(ch.index) else newSet.add(ch.index)
                                    viewModel.setSelectedChapters(newSet)
                                }
                                .padding(vertical = 2.dp)
                        ) {
                            Checkbox(checked = ch.index in state.selectedChapterIndices, onCheckedChange = null)
                            Text(
                                "${ch.index + 1}. ${ch.title}  (~${ch.wordCount} słów)",
                                style = MaterialTheme.typography.bodySmall,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                    }
                }
                Text(
                    "Zaznaczono: ${state.selectedChapterIndices.size}/${state.audiobookChapters.size}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = { viewModel.confirmChapterSelection() },
                enabled = state.selectedChapterIndices.isNotEmpty(),
            ) { Text("🎧 Generuj (${state.selectedChapterIndices.size})") }
        },
        dismissButton = { TextButton(onClick = { viewModel.dismissChapterSelector() }) { Text("Anuluj") } },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LanguageDropdown(label: String, value: String, onValueChange: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val filtered = LANGUAGES.filter { it.contains(value, ignoreCase = true) }

    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = value,
            onValueChange = { onValueChange(it); expanded = true },
            label = { Text(label) },
            modifier = Modifier.fillMaxWidth().menuAnchor(),
            singleLine = true,
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
        )
        ExposedDropdownMenu(expanded = expanded && filtered.isNotEmpty(), onDismissRequest = { expanded = false }) {
            filtered.take(10).forEach { lang ->
                DropdownMenuItem(
                    text = { Text(lang) },
                    onClick = { onValueChange(lang); expanded = false },
                )
            }
        }
    }
}
