package com.rebook.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.*
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rebook.app.ui.ConversionViewModel
import com.rebook.app.ui.HomeScreen
import com.rebook.app.ui.SettingsScreen
import com.rebook.app.ui.theme.ReBookTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            ReBookTheme {
                val viewModel: ConversionViewModel = viewModel()
                var showSettings by remember { mutableStateOf(false) }
                val state by viewModel.state.collectAsState()

                if (showSettings) {
                    SettingsScreen(
                        currentConfig = state.config,
                        onSave = { viewModel.saveConfig(it) },
                        onBack = { showSettings = false },
                    )
                } else {
                    HomeScreen(
                        viewModel = viewModel,
                        onOpenSettings = { showSettings = true },
                    )
                }
            }
        }
    }
}
