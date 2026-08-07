package com.jonbj.alembic.monitor.ui.theme

import android.app.Activity
import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat

private val DarkColorScheme = darkColorScheme(
    primary = Mint400,
    onPrimary = Mint950,
    primaryContainer = Mint950,
    onPrimaryContainer = Mint400,
    secondary = Sky400,
    onSecondary = Ink950,
    secondaryContainer = Sky900,
    onSecondaryContainer = Ink100,
    tertiary = Amber400,
    onTertiary = Ink950,
    tertiaryContainer = Amber900,
    onTertiaryContainer = Ink100,
    error = Coral400,
    onError = Ink950,
    errorContainer = Coral900,
    onErrorContainer = Ink100,
    background = Ink950,
    onBackground = Ink100,
    surface = Ink900,
    onSurface = Ink100,
    surfaceVariant = Ink850,
    onSurfaceVariant = Ink300,
    outline = Ink600,
    outlineVariant = Ink800,
    inverseSurface = Ink100,
    inverseOnSurface = Ink900,
    inversePrimary = Mint700,
    surfaceTint = Mint400
)

private val LightColorScheme = lightColorScheme(
    primary = Mint700,
    onPrimary = PaperSurface,
    primaryContainer = ColorTokens.LightMint,
    onPrimaryContainer = Mint950,
    secondary = ColorTokens.LightSky,
    onSecondary = PaperSurface,
    secondaryContainer = ColorTokens.LightSkyContainer,
    onSecondaryContainer = PaperText,
    tertiary = ColorTokens.LightAmber,
    onTertiary = PaperSurface,
    tertiaryContainer = ColorTokens.LightAmberContainer,
    onTertiaryContainer = PaperText,
    error = ColorTokens.LightError,
    onError = PaperSurface,
    errorContainer = ColorTokens.LightErrorContainer,
    onErrorContainer = Coral900,
    background = Paper,
    onBackground = PaperText,
    surface = PaperSurface,
    onSurface = PaperText,
    surfaceVariant = PaperRaised,
    onSurfaceVariant = ColorTokens.LightMutedText,
    outline = PaperOutline,
    outlineVariant = ColorTokens.LightOutlineVariant,
    surfaceTint = Mint700
)

private object ColorTokens {
    val LightMint = androidx.compose.ui.graphics.Color(0xFFC2F3E3)
    val LightSky = androidx.compose.ui.graphics.Color(0xFF2D668F)
    val LightSkyContainer = androidx.compose.ui.graphics.Color(0xFFD0E9FA)
    val LightAmber = androidx.compose.ui.graphics.Color(0xFF805500)
    val LightAmberContainer = androidx.compose.ui.graphics.Color(0xFFFFE3B2)
    val LightError = androidx.compose.ui.graphics.Color(0xFFB3261E)
    val LightErrorContainer = androidx.compose.ui.graphics.Color(0xFFFFDAD6)
    val LightMutedText = androidx.compose.ui.graphics.Color(0xFF4F6575)
    val LightOutlineVariant = androidx.compose.ui.graphics.Color(0xFFC8D4DC)
}

private val AlembicShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(18.dp),
    large = RoundedCornerShape(24.dp),
    extraLarge = RoundedCornerShape(30.dp)
)

@Composable
fun AlembicMonitorTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = false,
    content: @Composable () -> Unit
) {
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkColorScheme
        else -> LightColorScheme
    }
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = colorScheme.background.toArgb()
            window.navigationBarColor = colorScheme.surface.toArgb()
            WindowCompat.getInsetsController(window, view).apply {
                isAppearanceLightStatusBars = !darkTheme
                isAppearanceLightNavigationBars = !darkTheme
            }
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        shapes = AlembicShapes,
        content = content
    )
}
