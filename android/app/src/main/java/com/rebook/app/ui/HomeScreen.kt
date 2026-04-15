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
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.ui.graphics.StrokeCap
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

/**
 * Wizard action definition — each represents an entry on Screen 1 ("Choose action").
 */
private data class WizardAction(
    val id: String,
    val icon: String,
    val title: String,
    val desc: String,
    val badgeText: String,
    val badgeColor: Color,
    val hasLang: Boolean = false,
    val hasFormat: Boolean = false,
    val hasVerify: Boolean = false,
    val hasVoice: Boolean = false,
    val hasPageRange: Boolean = false,
    val hasCorrection: Boolean = false,
)

// ════════════════════════════════════════════════════════════════════════════
// Main Screen — Wizard Flow
// ════════════════════════════════════════════════════════════════════════════

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    viewModel: ConversionViewModel,
    onOpenSettings: () -> Unit,
) {
    val state by viewModel.state.collectAsState()
    val context = LocalContext.current

    // ── Wizard state ─────────────────────────────────────────────────────
    // 0=pick file, 1=choose action, 2=options, 3=progress, 4=done
    var wizardStep by remember { mutableIntStateOf(0) }
    var selectedAction by remember { mutableStateOf<WizardAction?>(null) }

    // Auto-advance to progress when conversion starts
    LaunchedEffect(state.isConverting) {
        if (state.isConverting && wizardStep < 3) wizardStep = 3
    }
    // Auto-advance to done when finished
    LaunchedEffect(state.outputPath) {
        if (state.outputPath != null && !state.isConverting) wizardStep = 4
    }

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
            wizardStep = 1  // auto-advance after picking file
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

    // ── About dialog ─────────────────────────────────────────────────────
    var showAbout by remember { mutableStateOf(false) }
    if (showAbout) {
        AlertDialog(
            onDismissRequest = { showAbout = false },
            title = { Text(stringResource(R.string.about_title)) },
            text = {
                Column {
                    Text(stringResource(R.string.about_version, "3.15.0"),
                        style = MaterialTheme.typography.labelMedium, color = RbPrimary)
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

    // ── Build actions list based on file type ────────────────────────────
    val actions = remember(state.isPdf, state.selectedFileName) {
        val ext = state.selectedFileName.substringAfterLast('.', "").lowercase()
        when {
            state.isPdf -> listOf(
                WizardAction("convert", "📖", "Zamień na eBooka", "OCR + konwersja do EPUB/HTML/MD", "OCR", RbSecondary, hasFormat = true, hasPageRange = true, hasCorrection = true),
                WizardAction("translate_epub", "🌐", "Przetłumacz i zamień na eBooka", "OCR + tłumaczenie AI → EPUB", "AI", RbPrimary, hasLang = true, hasVerify = true, hasFormat = true, hasPageRange = true),
                WizardAction("translate_pdf", "📄", "Przetłumacz PDF", "Zachowuje układ, czcionki i grafikę", "NOWE", RbTertiary, hasLang = true, hasPageRange = true),
                WizardAction("audiobook", "🎧", "Wygeneruj Audiobooka", "OCR → synteza mowy TTS", "TTS", RbTertiary, hasVoice = true, hasPageRange = true),
                WizardAction("full_pipeline", "✨", "Przetłumacz → eBook → Audio", "Pełny pipeline all-in-one", "ALL", RbPrimary, hasLang = true, hasVerify = true, hasVoice = true, hasPageRange = true),
            )
            ext == "epub" -> listOf(
                WizardAction("translate_epub", "🌐", "Przetłumacz EPUB", "Zachowuje rozdziały i okładkę", "AI", RbPrimary, hasLang = true, hasVerify = true),
                WizardAction("audiobook", "🎧", "Zamień na Audiobooka", "Synteza mowy z EPUB", "TTS", RbTertiary, hasVoice = true),
            )
            else -> listOf(
                WizardAction("convert", "📖", "Zamień na eBooka", "Markdown → EPUB/HTML", "Szybko", RbSecondary, hasFormat = true),
                WizardAction("translate_epub", "🌐", "Przetłumacz i zamień na eBooka", "Tłumaczenie AI + konwersja", "AI", RbPrimary, hasLang = true, hasVerify = true, hasFormat = true),
                WizardAction("audiobook", "🎧", "Zamień na Audiobooka", "Synteza mowy z Markdown", "TTS", RbTertiary, hasVoice = true),
            )
        }
    }

    val topTitles = listOf("ReBook", "Wybierz akcję", "Opcje", "W toku…", "Gotowe!")

    Scaffold(
        topBar = {
            Column {
                TopAppBar(
                    navigationIcon = {
                        if (wizardStep > 0 && wizardStep < 3) {
                            IconButton(onClick = {
                                wizardStep = (wizardStep - 1).coerceAtLeast(0)
                            }) {
                                Icon(Icons.Default.ArrowBack, "Back", tint = RbOnSurface2)
                            }
                        }
                    },
                    title = {
                        if (wizardStep == 0) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text("ReBook", style = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.ExtraBold), color = RbPrimary)
                                Spacer(Modifier.width(8.dp))
                                Surface(shape = RoundedCornerShape(6.dp), color = RbPrimary.copy(alpha = 0.15f)) {
                                    Text("v3.15", modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp), style = MaterialTheme.typography.labelSmall, color = RbPrimary)
                                }
                            }
                        } else {
                            Text(topTitles.getOrElse(wizardStep) { "ReBook" }, style = MaterialTheme.typography.titleLarge, color = RbOnSurface)
                        }
                    },
                    actions = {
                        IconButton(onClick = { showAbout = true }) { Icon(Icons.Default.Info, "About", tint = RbOnSurface3) }
                        IconButton(onClick = onOpenSettings) { Icon(Icons.Default.Settings, "Settings", tint = RbOnSurface2) }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.Transparent),
                )

                // ── Step progress segments ───────────────────────────────
                AnimatedVisibility(visible = wizardStep in 1..4) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 4.dp),
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        for (i in 0..3) {
                            Box(
                                modifier = Modifier
                                    .weight(1f)
                                    .height(3.dp)
                                    .clip(RoundedCornerShape(2.dp))
                                    .background(RbOutline)
                            ) {
                                val fraction = when {
                                    i < wizardStep - 1 -> 1f
                                    i == wizardStep - 1 -> if (wizardStep == 3) state.progressPercent else 0.5f
                                    else -> 0f
                                }
                                Box(
                                    modifier = Modifier
                                        .fillMaxHeight()
                                        .fillMaxWidth(fraction)
                                        .background(
                                            Brush.horizontalGradient(listOf(RbPrimary, RbPrimary.copy(alpha = 0.7f)))
                                        )
                                )
                            }
                        }
                    }
                    Spacer(Modifier.height(4.dp))
                }
            }
        },
        containerColor = RbBackground,
    ) { padding ->

        // ── File chip — visible on steps 1-3 ────────────────────────────
        Column(
            modifier = Modifier.fillMaxSize().padding(padding),
        ) {
            AnimatedVisibility(visible = wizardStep in 1..3 && state.selectedFileUri != null) {
                FileChip(
                    name = state.selectedFileName,
                    size = state.selectedFileSize,
                    isPdf = state.isPdf,
                )
            }

            // ── Screen Content ───────────────────────────────────────────
            AnimatedContent(
                targetState = wizardStep,
                transitionSpec = {
                    val enter = fadeIn() + slideInHorizontally { if (targetState > initialState) it / 3 else -it / 3 }
                    val exit = fadeOut() + slideOutHorizontally { if (targetState > initialState) -it / 3 else it / 3 }
                    enter togetherWith exit
                },
                label = "wizard",
            ) { step ->
                when (step) {
                    0 -> ScreenPickFile(onPick = {
                        filePicker.launch(arrayOf("application/pdf", "application/epub+zip", "text/markdown"))
                    })
                    1 -> ScreenChooseAction(actions = actions, onSelect = { action ->
                        selectedAction = action
                        // Configure viewModel based on action
                        when (action.id) {
                            "convert" -> {
                                viewModel.setTranslate(false)
                                viewModel.setTranslatePdf(false)
                                viewModel.setUseAi(true)
                            }
                            "translate_epub" -> {
                                viewModel.setTranslate(true)
                                viewModel.setTranslatePdf(false)
                                viewModel.setUseAi(true)
                            }
                            "translate_pdf" -> {
                                viewModel.setTranslate(true)
                                viewModel.setTranslatePdf(true)
                            }
                            "audiobook" -> {
                                viewModel.setTranslate(false)
                                viewModel.setTranslatePdf(false)
                            }
                            "full_pipeline" -> {
                                viewModel.setTranslate(true)
                                viewModel.setTranslatePdf(false)
                                viewModel.setUseAi(true)
                                viewModel.setPipelineAutoAudiobook(true)
                            }
                        }
                        wizardStep = 2
                    })
                    2 -> ScreenOptions(
                        action = selectedAction,
                        state = state,
                        viewModel = viewModel,
                        onStart = {
                            if (selectedAction?.id == "audiobook") {
                                viewModel.startAudiobook()
                            } else {
                                viewModel.startConversion()
                            }
                            wizardStep = 3
                        },
                    )
                    3 -> ScreenProgress(state = state, viewModel = viewModel, action = selectedAction)
                    4 -> ScreenDone(
                        state = state,
                        viewModel = viewModel,
                        saveLauncher = saveLauncher,
                        epubPickerForAudiobook = epubPickerForAudiobook,
                        context = context,
                        onNewFile = {
                            viewModel.removeFile()
                            selectedAction = null
                            wizardStep = 0
                        },
                    )
                }
            }
        }
    }
}

// ════════════════════════════════════════════════════════════════════════════
// Screen 0 — Pick File
// ════════════════════════════════════════════════════════════════════════════

@Composable
private fun ScreenPickFile(onPick: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .height(260.dp)
                .clickable(onClick = onPick),
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = Color.Transparent),
            border = CardDefaults.outlinedCardBorder().copy(
                brush = Brush.linearGradient(listOf(RbPrimary.copy(alpha = 0.3f), RbPrimary.copy(alpha = 0.1f)))
            ),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(
                        Brush.radialGradient(
                            listOf(RbPrimary.copy(alpha = 0.06f), Color.Transparent),
                        )
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("📥", fontSize = 52.sp)
                    Spacer(Modifier.height(12.dp))
                    Text("Wybierz plik", style = MaterialTheme.typography.titleLarge, color = RbOnSurface)
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        FormatTag("PDF", RbTertiary)
                        FormatTag("EPUB", RbSecondary)
                        FormatTag("MD", RbPrimary)
                    }
                    Spacer(Modifier.height(16.dp))
                    OutlinedButton(
                        onClick = onPick,
                        shape = RoundedCornerShape(20.dp),
                        border = ButtonDefaults.outlinedButtonBorder.copy(brush = Brush.linearGradient(listOf(RbOutline, RbOutline))),
                    ) {
                        Text("📂 Przeglądaj pliki", color = RbPrimary, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }
}

@Composable
private fun FormatTag(label: String, color: Color) {
    Surface(
        shape = RoundedCornerShape(20.dp),
        color = color.copy(alpha = 0.15f),
        border = ButtonDefaults.outlinedButtonBorder.copy(brush = Brush.linearGradient(listOf(color.copy(alpha = 0.25f), color.copy(alpha = 0.1f)))),
    ) {
        Text(label, modifier = Modifier.padding(horizontal = 10.dp, vertical = 3.dp),
            style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold, letterSpacing = 0.4.sp),
            color = color)
    }
}

// ════════════════════════════════════════════════════════════════════════════
// Screen 1 — Choose Action
// ════════════════════════════════════════════════════════════════════════════

@Composable
private fun ScreenChooseAction(actions: List<WizardAction>, onSelect: (WizardAction) -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp)
            .verticalScroll(rememberScrollState()),
    ) {
        Text("CO CHCESZ ZROBIĆ?", style = MaterialTheme.typography.labelSmall.copy(
            fontWeight = FontWeight.Bold, letterSpacing = 0.8.sp),
            color = RbOnSurface3)
        Spacer(Modifier.height(12.dp))

        actions.forEach { action ->
            ActionItem(action = action, onClick = { onSelect(action) })
            Spacer(Modifier.height(8.dp))
        }

        Spacer(Modifier.height(32.dp))
    }
}

@Composable
private fun ActionItem(action: WizardAction, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = RbCard),
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Icon circle
            Surface(
                shape = RoundedCornerShape(14.dp),
                color = RbPrimary.copy(alpha = 0.12f),
                modifier = Modifier.size(46.dp),
            ) {
                Box(contentAlignment = Alignment.Center, modifier = Modifier.fillMaxSize()) {
                    Text(action.icon, fontSize = 22.sp)
                }
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(action.title, style = MaterialTheme.typography.titleMedium, color = RbOnSurface)
                Text(action.desc, style = MaterialTheme.typography.bodySmall, color = RbOnSurface2, maxLines = 2)
            }
            Spacer(Modifier.width(8.dp))
            // Badge
            Surface(
                shape = RoundedCornerShape(10.dp),
                color = action.badgeColor.copy(alpha = 0.15f),
            ) {
                Text(action.badgeText,
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                    style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold, fontSize = 10.sp),
                    color = action.badgeColor)
            }
            Spacer(Modifier.width(4.dp))
            Text("›", color = RbOnSurface3, fontSize = 16.sp)
        }
    }
}

// ════════════════════════════════════════════════════════════════════════════
// Screen 2 — Options
// ════════════════════════════════════════════════════════════════════════════

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ScreenOptions(
    action: WizardAction?,
    state: ConversionState,
    viewModel: ConversionViewModel,
    onStart: () -> Unit,
) {
    if (action == null) return

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp)
            .verticalScroll(rememberScrollState()),
    ) {
        // ── Language card ────────────────────────────────────────────────
        if (action.hasLang) {
            OptionsCard(title = "JĘZYKI") {
                LanguageDropdown(label = "Z języka", value = state.langFrom, onValueChange = { viewModel.setLangFrom(it) })
                Spacer(Modifier.height(6.dp))
                LanguageDropdown(label = "Na język", value = state.langTo, onValueChange = { viewModel.setLangTo(it) })
            }
            Spacer(Modifier.height(10.dp))
        }

        // ── Format card ─────────────────────────────────────────────────
        if (action.hasFormat) {
            OptionsCard(title = "FORMAT WYJŚCIOWY") {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
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
            }
            Spacer(Modifier.height(10.dp))
        }

        // ── Page range card (PDF) ───────────────────────────────────────
        if (action.hasPageRange && state.isPdf) {
            OptionsCard(title = "ZAKRES STRON") {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    OutlinedTextField(
                        value = state.pageStart,
                        onValueChange = { viewModel.setPageStart(it.filter { c -> c.isDigit() }) },
                        label = { Text("Od") },
                        modifier = Modifier.width(80.dp),
                        singleLine = true,
                    )
                    Text("–", color = RbOnSurface3, fontSize = 18.sp)
                    OutlinedTextField(
                        value = state.pageEnd,
                        onValueChange = { viewModel.setPageEnd(it.filter { c -> c.isDigit() }) },
                        label = { Text("Do") },
                        modifier = Modifier.width(80.dp),
                        singleLine = true,
                    )
                    if (state.totalPageCount > 0) {
                        Text("z ${state.totalPageCount}", style = MaterialTheme.typography.labelSmall, color = RbOnSurface3)
                    }
                }
            }
            Spacer(Modifier.height(10.dp))
        }

        // ── Toggles card ────────────────────────────────────────────────
        val hasToggles = action.hasCorrection || action.hasVerify
        if (hasToggles) {
            OptionsCard(title = "OPCJE") {
                if (action.hasCorrection) {
                    ToggleRow("🤖 Korekta AI", "Poprawia OCR za pomocą LLM", state.useAi) { viewModel.setUseAi(it) }
                }
                if (action.hasVerify) {
                    ToggleRow("✅ Weryfikacja", "Dwuprzebiegowa kontrola jakości", state.verify) { viewModel.setVerify(it) }
                }
            }
            Spacer(Modifier.height(10.dp))
        }

        // ── Voice card ──────────────────────────────────────────────────
        if (action.hasVoice) {
            val currentVoices = remember(state.langTo) { TtsEngine.voicesFor(state.langTo) }
            val voiceKeys = currentVoices.keys.toList()
            val voiceLabels = currentVoices.values.toList()

            LaunchedEffect(state.langTo) {
                val firstKey = voiceKeys.firstOrNull()
                if (firstKey != null && state.ttsVoice !in currentVoices) viewModel.setTtsVoice(firstKey)
            }

            OptionsCard(title = "🎙 GŁOS TTS") {
                voiceKeys.forEachIndexed { i, key ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(8.dp))
                            .clickable { viewModel.setTtsVoice(key) }
                            .background(if (state.ttsVoice == key) RbPrimary.copy(alpha = 0.12f) else Color.Transparent)
                            .padding(horizontal = 12.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        RadioButton(selected = state.ttsVoice == key, onClick = { viewModel.setTtsVoice(key) },
                            colors = RadioButtonDefaults.colors(selectedColor = RbTertiary))
                        Spacer(Modifier.width(8.dp))
                        Text(voiceLabels[i], style = MaterialTheme.typography.bodyMedium, color = RbOnSurface)
                    }
                }
                Spacer(Modifier.height(4.dp))
                FilledTonalButton(
                    onClick = { viewModel.playSample() },
                    enabled = !state.isSamplePlaying,
                ) {
                    if (state.isSamplePlaying) CircularProgressIndicator(Modifier.size(14.dp), strokeWidth = 2.dp, color = RbTertiary)
                    else Icon(Icons.Default.PlayArrow, null, Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("Odsłuchaj próbkę")
                }
            }
            Spacer(Modifier.height(10.dp))
        }

        Spacer(Modifier.height(16.dp))

        // ── Start FAB ───────────────────────────────────────────────────
        Button(
            onClick = onStart,
            modifier = Modifier.fillMaxWidth().height(52.dp),
            shape = RoundedCornerShape(100.dp),
            colors = ButtonDefaults.buttonColors(containerColor = RbPrimary),
            elevation = ButtonDefaults.buttonElevation(defaultElevation = 6.dp),
        ) {
            Text("▶  Rozpocznij", fontSize = 15.sp, fontWeight = FontWeight.Bold, color = RbOnPrimary)
        }

        Spacer(Modifier.height(32.dp))
    }
}

@Composable
private fun OptionsCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = RbCard),
    ) {
        Column(Modifier.padding(14.dp)) {
            Text(title, style = MaterialTheme.typography.labelSmall.copy(
                fontWeight = FontWeight.Bold, letterSpacing = 0.6.sp),
                color = RbOnSurface3)
            Spacer(Modifier.height(8.dp))
            content()
        }
    }
}

@Composable
private fun ToggleRow(title: String, subtitle: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyMedium, color = RbOnSurface)
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = RbOnSurface3)
        }
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange,
            colors = SwitchDefaults.colors(checkedThumbColor = RbPrimary, checkedTrackColor = RbPrimary.copy(alpha = 0.3f)),
        )
    }
}

// ════════════════════════════════════════════════════════════════════════════
// Screen 3 — Progress
// ════════════════════════════════════════════════════════════════════════════

@Composable
private fun ScreenProgress(state: ConversionState, viewModel: ConversionViewModel, action: WizardAction?) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        // Circular progress ring
        Box(contentAlignment = Alignment.Center) {
            CircularProgressIndicator(
                progress = { state.progressPercent.coerceIn(0f, 1f) },
                modifier = Modifier.size(120.dp),
                strokeWidth = 6.dp,
                color = RbPrimary,
                trackColor = RbOutline,
                strokeCap = StrokeCap.Round,
            )
            Text(
                "${(state.progressPercent * 100).toInt()}%",
                style = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.Bold),
                color = RbOnSurface,
            )
        }

        Spacer(Modifier.height(20.dp))
        Text(
            state.progressStage.replaceFirstChar { it.uppercase() },
            style = MaterialTheme.typography.titleMedium,
            color = RbOnSurface,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            state.progressMessage,
            style = MaterialTheme.typography.bodySmall,
            color = RbOnSurface2,
            modifier = Modifier.padding(horizontal = 32.dp),
        )

        Spacer(Modifier.height(24.dp))

        // Stage list
        if (state.logMessages.isNotEmpty()) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(8.dp),
                colors = CardDefaults.cardColors(containerColor = RbCard),
            ) {
                Column(
                    Modifier.padding(12.dp).heightIn(max = 160.dp).verticalScroll(rememberScrollState()),
                ) {
                    state.logMessages.takeLast(10).forEach { msg ->
                        Text(msg, style = MaterialTheme.typography.bodySmall.copy(
                            fontFamily = FontFamily.Monospace, fontSize = 10.sp, color = RbOnSurface3))
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))

        // Stop button
        if (state.isConverting || state.isGeneratingAudiobook) {
            OutlinedButton(
                onClick = {
                    if (state.isGeneratingAudiobook) viewModel.cancelAudiobook()
                    else viewModel.stopConversion()
                },
                shape = RoundedCornerShape(100.dp),
                border = ButtonDefaults.outlinedButtonBorder.copy(brush = Brush.linearGradient(listOf(RbError, RbError))),
            ) { Text("⛔ Zatrzymaj", color = RbError) }
        }

        // Error display
        if (state.error != null) {
            Spacer(Modifier.height(8.dp))
            Text("❌ ${state.error}", style = MaterialTheme.typography.bodySmall, color = RbError)
        }
    }
}

// ════════════════════════════════════════════════════════════════════════════
// Screen 4 — Done
// ════════════════════════════════════════════════════════════════════════════

@Composable
private fun ScreenDone(
    state: ConversionState,
    viewModel: ConversionViewModel,
    saveLauncher: androidx.activity.result.ActivityResultLauncher<String>,
    epubPickerForAudiobook: androidx.activity.result.ActivityResultLauncher<Array<String>>,
    context: android.content.Context,
    onNewFile: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(32.dp))
        Text("✅", fontSize = 60.sp)
        Spacer(Modifier.height(12.dp))
        Text("Gotowe!", style = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.Bold), color = RbOnSurface)
        Spacer(Modifier.height(8.dp))
        state.outputPath?.let { path ->
            Surface(shape = RoundedCornerShape(10.dp), color = RbCard) {
                Text(
                    File(path).name,
                    modifier = Modifier.padding(horizontal = 18.dp, vertical = 8.dp),
                    style = MaterialTheme.typography.bodySmall,
                    color = RbOnSurface2,
                )
            }
        }

        Spacer(Modifier.height(20.dp))

        // Action buttons
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(
                onClick = onNewFile,
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(100.dp),
            ) { Text("+ Nowy", color = RbOnSurface2) }

            FilledTonalButton(
                onClick = {
                    state.outputPath?.let { path ->
                        val file = File(path)
                        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
                        val intent = Intent(Intent.ACTION_VIEW).apply {
                            setDataAndType(uri, when (file.extension) {
                                "epub" -> "application/epub+zip"; "html" -> "text/html"; else -> "text/plain"
                            })
                            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        }
                        context.startActivity(intent)
                    }
                },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(100.dp),
            ) { Text("📂 Otwórz") }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
            FilledTonalButton(
                onClick = { state.outputPath?.let { saveLauncher.launch(File(it).name) } },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(100.dp),
            ) {
                Icon(Icons.Default.Save, null, Modifier.size(16.dp))
                Spacer(Modifier.width(4.dp))
                Text("Zapisz")
            }
            FilledTonalButton(
                onClick = {
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
                },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(100.dp),
            ) {
                Icon(Icons.Default.Share, null, Modifier.size(16.dp))
                Spacer(Modifier.width(4.dp))
                Text("Udostępnij")
            }
        }

        // ── Audiobook panel ─────────────────────────────────────────────
        val epubReady = state.outputPath?.endsWith(".epub") == true
                || state.audiobookEpubUri != null

        if (epubReady) {
            Spacer(Modifier.height(20.dp))
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = RbSecondaryContainer),
                border = CardDefaults.outlinedCardBorder().copy(
                    brush = Brush.linearGradient(listOf(RbSecondary.copy(alpha = 0.3f), RbPrimary.copy(alpha = 0.15f)))
                ),
            ) {
                Column(Modifier.padding(14.dp)) {
                    Text("🎧 Wygenerować audiobooka?", style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold), color = RbSecondary)
                    Spacer(Modifier.height(8.dp))

                    val currentVoices = remember(state.langTo) { TtsEngine.voicesFor(state.langTo) }
                    val voiceKeys = currentVoices.keys.toList()
                    val voiceLabels = currentVoices.values.toList()

                    LaunchedEffect(state.langTo) {
                        val firstKey = voiceKeys.firstOrNull()
                        if (firstKey != null && state.ttsVoice !in currentVoices) viewModel.setTtsVoice(firstKey)
                    }

                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        var voiceExpanded by remember { mutableStateOf(false) }
                        val selectedLabel = currentVoices[state.ttsVoice] ?: voiceLabels.firstOrNull() ?: ""

                        ExposedDropdownMenuBox(
                            expanded = voiceExpanded,
                            onExpandedChange = { voiceExpanded = !voiceExpanded },
                            modifier = Modifier.weight(1f),
                        ) {
                            OutlinedTextField(
                                value = selectedLabel,
                                onValueChange = {},
                                readOnly = true,
                                modifier = Modifier.menuAnchor().fillMaxWidth(),
                                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(voiceExpanded) },
                                textStyle = MaterialTheme.typography.bodySmall,
                            )
                            ExposedDropdownMenu(expanded = voiceExpanded, onDismissRequest = { voiceExpanded = false }) {
                                voiceKeys.forEachIndexed { i, key ->
                                    DropdownMenuItem(
                                        text = { Text(voiceLabels[i]) },
                                        onClick = { viewModel.setTtsVoice(key); voiceExpanded = false },
                                    )
                                }
                            }
                        }
                        FilledTonalButton(
                            onClick = { viewModel.startAudiobook() },
                            shape = RoundedCornerShape(100.dp),
                            colors = ButtonDefaults.filledTonalButtonColors(containerColor = RbSecondary.copy(alpha = 0.2f)),
                        ) { Text("▶", color = RbSecondary) }
                    }

                    // Audiobook progress
                    if (state.audiobookProgress.isNotBlank()) {
                        Spacer(Modifier.height(4.dp))
                        Text(state.audiobookProgress, style = MaterialTheme.typography.bodySmall, color = RbOnSurface2)
                    }
                    if (state.isGeneratingAudiobook) {
                        LinearProgressIndicator(
                            progress = { if (state.audiobookProgressPercent < 0f) 0f else state.audiobookProgressPercent },
                            modifier = Modifier.fillMaxWidth().padding(top = 8.dp).clip(RoundedCornerShape(4.dp)),
                            color = RbSecondary,
                        )
                    }
                }
            }
        }

        Spacer(Modifier.height(40.dp))
    }
}

// ════════════════════════════════════════════════════════════════════════════
// Shared Components
// ════════════════════════════════════════════════════════════════════════════

@Composable
private fun FileChip(name: String, size: String, isPdf: Boolean) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 4.dp)
            .background(RbSurface2, RoundedCornerShape(8.dp))
            .padding(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(if (isPdf) "📕" else if (name.endsWith(".epub", true)) "📗" else "📘", fontSize = 20.sp)
        Spacer(Modifier.width(10.dp))
        Column {
            Text(name, style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.SemiBold), color = RbOnSurface, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(size, style = MaterialTheme.typography.labelSmall, color = RbOnSurface2)
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
                Text("Znaleziono ${state.audiobookChapters.size} rozdziałów.", style = MaterialTheme.typography.bodySmall)
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
                Column(modifier = Modifier.heightIn(max = 350.dp).verticalScroll(rememberScrollState())) {
                    state.audiobookChapters.forEach { ch ->
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.fillMaxWidth().clickable {
                                val newSet = state.selectedChapterIndices.toMutableSet()
                                if (ch.index in newSet) newSet.remove(ch.index) else newSet.add(ch.index)
                                viewModel.setSelectedChapters(newSet)
                            }.padding(vertical = 2.dp)
                        ) {
                            Checkbox(checked = ch.index in state.selectedChapterIndices, onCheckedChange = null)
                            Text("${ch.index + 1}. ${ch.title}  (~${ch.wordCount} słów)",
                                style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                    }
                }
                Text("Zaznaczono: ${state.selectedChapterIndices.size}/${state.audiobookChapters.size}",
                    style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(top = 4.dp))
            }
        },
        confirmButton = {
            TextButton(onClick = { viewModel.confirmChapterSelection() }, enabled = state.selectedChapterIndices.isNotEmpty()) {
                Text("🎧 Generuj (${state.selectedChapterIndices.size})")
            }
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
                DropdownMenuItem(text = { Text(lang) }, onClick = { onValueChange(lang); expanded = false })
            }
        }
    }
}
