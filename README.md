# Phonon

**Phonon** is a premium, lightweight Windows media controller featuring a physics-based "Dynamic Island" interface. It integrates natively with WinRT to provide a high-fidelity control experience with glassmorphism aesthetics and dynamic "Aura" lighting.

## Features

*   **Dynamic Island UI**: Expands and contracts with smooth physics-based animations.
*   **Native Integration**: Controls Spotify, Apple Music, Chrome, and any other system media.
*   **System Tray Support**: Minimizes to tray to keep your workspace clean.
*   **Media Controls**: Play/Pause, Next/Prev, Shuffle, Repeat, and Seek support.
*   **Album Art**: High-resolution album art display with adaptive background glow.
*   **Compact Mode**: "Island" mode for minimal distraction.

## Installation

1.  Download the latest `MediaIsland.exe` from the [Releases](https://github.com/Your_GitHub_Username/media-island-widget/releases) page.
2.  Run `MediaIsland.exe`.
3.  The widget will appear at the top of your screen.

## Development

This project uses `customtkinter` for the UI and `winrt` for media controls.

### Requirements

*   Python 3.10+
*   Windows 10/11

### Build

To build the executable yourself:

```bash
pip install -r requirements.txt
pyinstaller widget.spec
```
