import tkinter as tk
import subprocess
import os
import sys

# Define absolute paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WIDGET_SCRIPT = os.path.join(BASE_DIR, "widget.py")
SETTINGS_SCRIPT = os.path.join(BASE_DIR, "settings.py")
PYTHON_EXE = sys.executable

class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Media Controller")
        self.geometry("300x200")
        self.configure(bg="#1E1E1E")
        
        # Header
        lbl = tk.Label(self, text="Media Controller", bg="#1E1E1E", fg="white", font=("Segoe UI", 14, "bold"))
        lbl.pack(pady=20)
        
        # Buttons
        btn_widget = tk.Button(self, text="Start Widget", command=self.launch_widget, bg="#007BFF", fg="white", font=("Segoe UI", 10), width=20)
        btn_widget.pack(pady=5)

        btn_stop = tk.Button(self, text="Stop Widget", command=self.stop_widget, bg="#FF4444", fg="white", font=("Segoe UI", 10), width=20)
        btn_stop.pack(pady=5)
        
        btn_settings = tk.Button(self, text="Settings", command=self.launch_settings, bg="#444444", fg="white", font=("Segoe UI", 10), width=20)
        btn_settings.pack(pady=5)
        
        btn_exit = tk.Button(self, text="Exit Launcher", command=self.destroy, bg="#AA0000", fg="white", font=("Segoe UI", 10), width=20)
        btn_exit.pack(pady=5)
        
        self.widget_process = None

    def launch_widget(self):
        # Check if already running?
        if self.widget_process is None or self.widget_process.poll() is not None:
             # Use creationflags=subprocess.CREATE_NO_WINDOW if on Windows to allow background run without console popping up if pythonw isn't used or if needed
             self.widget_process = subprocess.Popen([PYTHON_EXE, WIDGET_SCRIPT])
             print("Widget started.")
        else:
             print("Widget already running.")

    def stop_widget(self):
        if self.widget_process and self.widget_process.poll() is None:
            self.widget_process.terminate()
            self.widget_process = None
            print("Widget stopped.")
        else:
            # Fallback: try to kill any process named python that is running widget.py? 
            # Ideally rely on the process handle we have.
            # For robust "kill all", one might use: taskkill /F /IM python.exe (risky for other python apps)
            # So we stick to the handle.
            print("Widget not running (via this launcher).")

    def launch_settings(self):
        subprocess.Popen([PYTHON_EXE, SETTINGS_SCRIPT])

if __name__ == "__main__":
    app = Launcher()
    app.mainloop()
