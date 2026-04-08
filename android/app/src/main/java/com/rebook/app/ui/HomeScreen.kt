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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import com.rebook.app.R
import com.rebook.app.domain.Converter
import java.io.File

val LANGUAGES = listOf(
    "polski", "angielski", "niemiecki", "francuski", "hiszpański",
    "portugalski", "włoski", "niderlandzki", "czeski", "słowacki",
    "ukraiński", "rosyjski", "węgierski", "rumuński", "chorwacki",
    "serbski", "turecki", "szwedzki", "norweski", "duński", "fiński",
    "chiński", "japoński", "wietnamski", "tajski", "arabski", "perski"
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    viewModel: ConversionViewModel,
    onOpenSettings: () -> Unit,
) {
    val state by viewModel.state.collectAsState()
    val context = LocalContext.current

    val filePicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        uri?.let {
            // Persist permission
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

    // SAF save launcher
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

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("ReBook", style = MaterialTheme.typography.headlineMedium)
                        Text(
                            stringResource(R.string.app_subtitle),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                },
                actions = {
                    IconButton(onClick = onOpenSettings) {
                        Icon(Icons.Default.Settings, contentDescription = "Settings")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                ),
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp),
        ) {
            Spacer(Modifier.height(8.dp))

            // ── File Selection ──
            AnimatedVisibility(visible = state.selectedFileUri == null) {
                DropZone(onClick = {
                    filePicker.launch(arrayOf("application/pdf", "application/epub+zip", "text/markdown"))
                })
            }

            AnimatedVisibility(visible = state.selectedFileUri != null) {
                FileBadge(
                    name = state.selectedFileName,
                    size = state.selectedFileSize,
                    onRemove = { viewModel.removeFile() },
                )
            }

            Spacer(Modifier.height(16.dp))

            // ── Options ──
            Text(
                stringResource(R.string.options_header),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.height(8.dp))

            // Format selector
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.format_label), style = MaterialTheme.typography.bodyMedium)
                Spacer(Modifier.weight(1f))
                SingleChoiceSegmentedButtonRow {
                    Converter.OutputFormat.entries.forEachIndexed { i, fmt ->
                        SegmentedButton(
                            selected = state.outputFormat == fmt,
                            onClick = { viewModel.setOutputFormat(fmt) },
                            shape = SegmentedButtonDefaults.itemShape(i, Converter.OutputFormat.entries.size),
                        ) { Text(fmt.name) }
                    }
                }
            }

            Spacer(Modifier.height(8.dp))

            // AI correction
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = state.useAi, onCheckedChange = { viewModel.setUseAi(it) })
                Text(stringResource(R.string.ai_check), style = MaterialTheme.typography.bodyMedium)
            }

            // Translation
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = state.translate, onCheckedChange = { viewModel.setTranslate(it) })
                Text(stringResource(R.string.translate_check), style = MaterialTheme.typography.bodyMedium)
            }

            // Language fields
            AnimatedVisibility(visible = state.translate) {
                Column(Modifier.padding(start = 32.dp)) {
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
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = state.translateImages, onCheckedChange = { viewModel.setTranslateImages(it) })
                        Text(stringResource(R.string.translate_images_check), style = MaterialTheme.typography.bodySmall)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = state.verify, onCheckedChange = { viewModel.setVerify(it) })
                        Text(stringResource(R.string.verify_check), style = MaterialTheme.typography.bodySmall)
                    }
                }
            }

            Spacer(Modifier.height(16.dp))

            // ── Convert + Stop Buttons ──
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = { viewModel.startConversion() },
                    enabled = state.selectedFileUri != null && !state.isConverting,
                    modifier = Modifier.weight(1f).height(48.dp),
                    shape = RoundedCornerShape(12.dp),
                ) {
                    Icon(Icons.Default.PlayArrow, null, Modifier.size(20.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(
                        if (state.isConverting) stringResource(R.string.converting_btn)
                        else stringResource(R.string.convert_btn)
                    )
                }

                AnimatedVisibility(visible = state.isConverting) {
                    FilledTonalButton(
                        onClick = { viewModel.stopConversion() },
                        modifier = Modifier.height(48.dp),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.filledTonalButtonColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer,
                        ),
                    ) {
                        Text("⛔ Stop")
                    }
                }
            }

            // ── Progress ──
            AnimatedVisibility(visible = state.isConverting || state.progressPercent > 0f) {
                Column(Modifier.padding(vertical = 12.dp)) {
                    LinearProgressIndicator(
                        progress = { state.progressPercent },
                        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(4.dp)),
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(
                        state.progressMessage,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            // ── Log ──
            if (state.logMessages.isNotEmpty() && state.isConverting) {
                Card(
                    modifier = Modifier.fillMaxWidth().heightIn(max = 150.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                ) {
                    Column(
                        Modifier.padding(8.dp).verticalScroll(rememberScrollState()),
                    ) {
                        state.logMessages.takeLast(20).forEach { msg ->
                            Text(msg, style = MaterialTheme.typography.bodySmall.copy(
                                fontFamily = FontFamily.Monospace, fontSize = 10.sp,
                            ))
                        }
                    }
                }
            }

            // ── Result ──
            AnimatedVisibility(visible = state.outputPath != null) {
                Card(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
                ) {
                    Column(Modifier.padding(16.dp)) {
                        Text(
                            "✅ ${stringResource(R.string.conversion_done)}",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onPrimaryContainer,
                        )
                        Spacer(Modifier.height(4.dp))
                        state.outputPath?.let { path ->
                            Text(
                                File(path).name,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f),
                            )
                        }
                        Spacer(Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            // Save to file
                            FilledTonalButton(onClick = {
                                state.outputPath?.let { path ->
                                    val file = File(path)
                                    saveLauncher.launch(file.name)
                                }
                            }) {
                                Icon(Icons.Default.Save, null, Modifier.size(18.dp))
                                Spacer(Modifier.width(4.dp))
                                Text(stringResource(R.string.save_btn))
                            }
                            // Share
                            FilledTonalButton(onClick = {
                                state.outputPath?.let { path ->
                                    val file = File(path)
                                    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
                                    val intent = Intent(Intent.ACTION_SEND).apply {
                                        type = when (file.extension) {
                                            "epub" -> "application/epub+zip"
                                            "html" -> "text/html"
                                            else -> "text/markdown"
                                        }
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
                            // Open
                            FilledTonalButton(onClick = {
                                state.outputPath?.let { path ->
                                    val file = File(path)
                                    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
                                    val intent = Intent(Intent.ACTION_VIEW).apply {
                                        setDataAndType(uri, when (file.extension) {
                                            "epub" -> "application/epub+zip"
                                            "html" -> "text/html"
                                            else -> "text/plain"
                                        })
                                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                    }
                                    context.startActivity(intent)
                                }
                            }) {
                                Icon(Icons.Default.MenuBook, null, Modifier.size(18.dp))
                                Spacer(Modifier.width(4.dp))
                                Text(stringResource(R.string.open_btn))
                            }
                        }
                    }
                }
            }

            // ── Error ──
            AnimatedVisibility(visible = state.error != null) {
                Card(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
                ) {
                    Text(
                        "❌ ${state.error}",
                        modifier = Modifier.padding(16.dp),
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                }
            }

            Spacer(Modifier.height(32.dp))
        }
    }
}

@Composable
private fun DropZone(onClick: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .height(140.dp)
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        border = CardDefaults.outlinedCardBorder(),
    ) {
        Column(
            modifier = Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Icon(Icons.Default.FileOpen, null, Modifier.size(40.dp), tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.height(8.dp))
            Text(stringResource(R.string.drop_title), style = MaterialTheme.typography.titleMedium)
            Text(
                stringResource(R.string.drop_subtitle),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun FileBadge(name: String, size: String, onRemove: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Default.Description, null, Modifier.size(32.dp), tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(name, style = MaterialTheme.typography.bodyLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(size, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            IconButton(onClick = onRemove) {
                Icon(Icons.Default.Close, stringResource(R.string.remove_btn))
            }
        }
    }
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
