package com.rebook.app.ui.theme

import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

private val ReBookDarkScheme = darkColorScheme(
    primary              = RbPrimary,
    onPrimary            = RbOnPrimary,
    primaryContainer     = RbPrimaryContainer,
    onPrimaryContainer   = RbOnPrimaryContainer,
    secondary            = RbSecondary,
    onSecondary          = RbOnSecondary,
    secondaryContainer   = RbSecondaryContainer,
    onSecondaryContainer = RbOnSecondaryContainer,
    tertiary             = RbTertiary,
    tertiaryContainer    = RbTertiaryContainer,
    onTertiaryContainer  = RbOnTertiaryContainer,
    background           = RbBackground,
    onBackground         = RbOnSurface,
    surface              = RbSurface,
    onSurface            = RbOnSurface,
    surfaceVariant       = RbSurfaceVariant,
    onSurfaceVariant     = RbOnSurfaceVariant,
    outline              = RbOutline,
    error                = RbError,
    errorContainer       = RbErrorContainer,
    onError              = RbOnError,
    onErrorContainer     = RbOnErrorContainer,
)

val ReBookTypography = Typography(
    headlineLarge  = TextStyle(fontSize = 28.sp, fontWeight = FontWeight.Bold,     lineHeight = 36.sp),
    headlineMedium = TextStyle(fontSize = 22.sp, fontWeight = FontWeight.Bold,     lineHeight = 28.sp),
    titleLarge     = TextStyle(fontSize = 18.sp, fontWeight = FontWeight.SemiBold, lineHeight = 24.sp),
    titleMedium    = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.SemiBold, lineHeight = 20.sp),
    bodyLarge      = TextStyle(fontSize = 16.sp, lineHeight = 24.sp),
    bodyMedium     = TextStyle(fontSize = 14.sp, lineHeight = 20.sp),
    bodySmall      = TextStyle(fontSize = 12.sp, lineHeight = 16.sp),
    labelLarge     = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.Medium,   lineHeight = 20.sp),
    labelSmall     = TextStyle(fontSize = 11.sp, lineHeight = 16.sp),
)

@Composable
fun ReBookTheme(content: @Composable () -> Unit) {
    // Always dark — matches the premium demo aesthetic
    MaterialTheme(
        colorScheme = ReBookDarkScheme,
        typography  = ReBookTypography,
        content     = content,
    )
}
