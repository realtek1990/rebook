package com.rebook.app.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.rebook.app.R
import com.rebook.app.data.AppConfig
import com.rebook.app.domain.AiProvider

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    currentConfig: AppConfig,
    onSave: (AppConfig) -> Unit,
    onBack: () -> Unit,
) {
    var provider by remember { mutableStateOf(currentConfig.llmProvider) }
    var model by remember { mutableStateOf(currentConfig.modelName) }
    var apiKey by remember { mutableStateOf(currentConfig.apiKey) }
    var kindleEmail by remember { mutableStateOf(currentConfig.kindleEmail) }

    val providerInfo = AiProvider.PROVIDERS
    val selectedProvider = providerInfo.find { it.key == provider }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.settings_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back")
                    }
                },
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
            // ── LLM Provider Section ──
            Text(
                stringResource(R.string.settings_llm_header),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.height(8.dp))

            // Provider dropdown
            var provExpanded by remember { mutableStateOf(false) }
            ExposedDropdownMenuBox(
                expanded = provExpanded,
                onExpandedChange = { provExpanded = it },
            ) {
                OutlinedTextField(
                    value = selectedProvider?.displayName ?: stringResource(R.string.settings_provider),
                    onValueChange = {},
                    readOnly = true,
                    label = { Text(stringResource(R.string.settings_provider)) },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(provExpanded) },
                    modifier = Modifier.fillMaxWidth().menuAnchor(),
                )
                ExposedDropdownMenu(expanded = provExpanded, onDismissRequest = { provExpanded = false }) {
                    providerInfo.forEach { p ->
                        DropdownMenuItem(
                            text = { Text(p.displayName) },
                            onClick = {
                                provider = p.key
                                model = p.models.firstOrNull() ?: ""
                                provExpanded = false
                            },
                        )
                    }
                }
            }
            Spacer(Modifier.height(8.dp))

            // Model
            AnimatedVisibility(visible = selectedProvider != null) {
                Column {
                    var modelExpanded by remember { mutableStateOf(false) }
                    ExposedDropdownMenuBox(
                        expanded = modelExpanded,
                        onExpandedChange = { modelExpanded = it },
                    ) {
                        OutlinedTextField(
                            value = model,
                            onValueChange = { model = it },
                            label = { Text(stringResource(R.string.settings_model)) },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(modelExpanded) },
                            modifier = Modifier.fillMaxWidth().menuAnchor(),
                            singleLine = true,
                        )
                        ExposedDropdownMenu(expanded = modelExpanded, onDismissRequest = { modelExpanded = false }) {
                            selectedProvider?.models?.forEach { m ->
                                DropdownMenuItem(
                                    text = { Text(m) },
                                    onClick = { model = m; modelExpanded = false },
                                )
                            }
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                }
            }

            // API Key
            OutlinedTextField(
                value = apiKey,
                onValueChange = { apiKey = it },
                label = { Text(stringResource(R.string.settings_api_key)) },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
            )

            Spacer(Modifier.height(24.dp))
            HorizontalDivider()
            Spacer(Modifier.height(16.dp))

            // ── Kindle Section ──
            Text(
                stringResource(R.string.settings_kindle_header),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.height(8.dp))

            OutlinedTextField(
                value = kindleEmail,
                onValueChange = { kindleEmail = it },
                label = { Text(stringResource(R.string.settings_kindle_email)) },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )

            Spacer(Modifier.height(24.dp))
            HorizontalDivider()
            Spacer(Modifier.height(16.dp))

            // ── OCR Info ──
            Text(
                stringResource(R.string.settings_ocr_header),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.height(8.dp))
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
            ) {
                Text(
                    stringResource(R.string.settings_ocr_info),
                    modifier = Modifier.padding(12.dp),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                )
            }

            Spacer(Modifier.height(32.dp))

            // ── Save / Cancel ──
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedButton(
                    onClick = onBack,
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(12.dp),
                ) {
                    Text(stringResource(R.string.settings_cancel))
                }
                Button(
                    onClick = {
                        onSave(AppConfig(
                            llmProvider = provider,
                            modelName = model,
                            apiKey = apiKey,
                            kindleEmail = kindleEmail,
                        ))
                        onBack()
                    },
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(12.dp),
                ) {
                    Text(stringResource(R.string.settings_save))
                }
            }

            Spacer(Modifier.height(32.dp))
        }
    }
}
