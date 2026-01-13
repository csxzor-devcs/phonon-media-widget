# Media Controller Widget - User Guide

A modern, auto-hiding media control widget for Windows 11. This widget sits at the top of your screen and reveals itself when you hover over it, mimicking the "Dynamic Island" allow you to control media playback (Spotify, Chrome, System Media) seamlessly.

## ✨ Features
- **Auto-Hide**: Disappears when not in use to save screen space.
- **Media Info**: Displays Album Art, Title, Artist, and Progress.
- **Controls**: Play/Pause, Next, Previous, and Seek/Progress Bar.
- **Settings GUI**: Customize size, colors, and behavior easily.
- **WinRT Integration**: Native Windows media control support.

## 🚀 Installation

### Prerequisites
- **Python 3.10+**: Ensure Python is installed and added to your PATH.

### Steps
1.  **Open Terminal**: Navigate to this project folder.
2.  **Install Dependencies**:
    Run the following command to install required libraries (`winrt`, `Pillow`, `customtkinter`):
    ```powershell
    pip install -r requirements.txt
    ```

## 🎮 How to Run (Easiest Method)
Double-click **`RunLauncher.bat`**. 
This opens a Control Panel where you can:
- **Start Widget**: Launches the media bar.
- **Stop Widget**: Instantly closes the running widget.
- **Settings**: Opens the configuration menu.
- **Exit Launcher**: Closes this control panel (the widget keeps running).

### Alternative Methods
- **Widget Only**: Double-click `RunWidget.bat`.
- **Settings Only**: Double-click `RunSettings.bat`.
- **Terminal**: Run `python main.py` or `python widget.py`.

## ⚙️ Configuration (Settings App)
The `settings.py` app allows you to tweak:
- **Geometry**: Width, Height, Corner Radius.
- **Appearance**: Toggle Album Art, Progress Bar, or Controls.
- **Behavior**:
    - **Animation Speed**: How fast the widget slides in/out.
    - **Hover Zone**: How close to the top edge you need to be to trigger it.

## 🕹️ Usage Controls
- **Hover**: Move mouse to top center of screen to show widget.
- **Click Art/Text**: (Currently decorative).
- **Play/Pause**: Click the center button.
- **Skip/Prev**: Click the arrow buttons.
- **Seek**: Click or Drag on the progress bar to specific timestamp.


## 🛑 How to Close
The closing method depends on how you started the widget:

### Method 1: Using `RunLauncher.bat` (Recommended)
Simply click the red **"Stop Widget"** button in the launcher window.

### Method 2: If running via Terminal (`python widget.py`)
1.  Click inside the terminal window.
2.  Press **`Ctrl+C`** on your keyboard.
3.  Or simply close the terminal window.

### Method 3: If running via `RunWidget.bat` (Hidden Terminal)
Since there is no visible window:
1.  Open **Task Manager** (`Ctrl+Shift+Esc`).
2.  Look for **"Python"** or **"pythonw.exe"** in the processes list.
3.  Right-click it and select **"End Task"**.
*(Note: A future update may add a right-click "Exit" menu to the widget)*

## 🛠️ Troubleshooting
- **Widget not showing?**
    - Ensure `python widget.py` is running in the terminal.
    - Move mouse to the very top (y=0) of the screen.
    - Check if `config.json` has valid values (or delete it to reset defaults).
- **"ImportError: No module named..."**
    - Run `pip install -r requirements.txt` again.
- **Media info incorrect?**
    - Run `python debug_media.py` to see what Windows is reporting. This helps distinguish between a widget bug and a Windows/App issue.
- **Album Art missing?**
    - Some media sources (like certain web players) might not provide high-res headers. The widget handles this by showing a placeholder.

## 📂 Project Structure
- `widget.py`: Main application logic.
- `settings.py`: Settings GUI.
- `debug_media.py`: Diagnostic tool for media issues.
- `main.py`: Launcher script.
- `RunLauncher.bat`: Main entry point (GUI Launcher).
- `RunWidget.bat`: Direct launcher for widget.
- `RunSettings.bat`: Direct launcher for settings.
- `config.json`: Stores user preferences.
- `poc.py`: Proof of Concept script (for developers).
- `requirements.txt`: List of dependencies.
