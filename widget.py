import tkinter as tk
import asyncio
import sys
import json
import threading
import subprocess
from ctypes import windll, Structure, c_long, byref, c_short, sizeof, Union
import time
import datetime
import io
import os
import ctypes
import math
from ctypes import wintypes
import pystray

# --- Ensure Pillow is Importable ---
try:
    from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageEnhance
except ImportError:
    print("CRITICAL: Pillow not installed. Run 'pip install Pillow'")
    sys.exit(1)

# --- High DPI Awareness ---
try:
    windll.shcore.SetProcessDpiAwareness(1) 
except Exception:
    pass

# --- WinRT Imports ---
try:
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
    import winrt.windows.storage.streams as streams
    import winrt.windows.security.cryptography as crypto
    WINRT_AVAILABLE = True
    # Non-critical import
    try:
        import winrt.windows.foundation.collections
    except:
        pass
except ImportError as e:
    print(f"WinRT import failed: {e}")
    WINRT_AVAILABLE = False
    GlobalSystemMediaTransportControlsSessionManager = None

# --- Mouse Polling Setup ---
class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]

def get_mouse_pos():
    pt = POINT()
    windll.user32.GetCursorPos(byref(pt))
    return pt.x, pt.y

# --- Process & Window Focusing ---
class FocusHelper:
    def __init__(self):
        self.user32 = windll.user32
        self.kernel32 = windll.kernel32
        self.psapi = windll.psapi
        
        # Constants
        self.WNDENUMPROC = windll.CFUNCTYPE(c_long, c_long, c_long)
        self.PROCESS_QUERY_INFORMATION = 0x0400
        self.PROCESS_VM_READ = 0x0010
        self.SW_RESTORE = 9
        self.SW_SHOW = 5
        
    def get_process_name(self, pid):
        hProcess = self.kernel32.OpenProcess(self.PROCESS_QUERY_INFORMATION | self.PROCESS_VM_READ, False, pid)
        if hProcess:
            from ctypes import create_unicode_buffer, wintypes
            # GetModuleBaseNameW is better for just the name
            buf = create_unicode_buffer(1024)
            if self.psapi.GetModuleBaseNameW(hProcess, 0, buf, 1024):
                 name = buf.value
                 self.kernel32.CloseHandle(hProcess)
                 return name
            self.kernel32.CloseHandle(hProcess)
        return ""

    def focus_app(self, app_id):
        # app_id is usually like "Spotify.exe" or "Microsoft.ZuneMusic_..."
        print(f"DEBUG: Attempting to focus AppID: {app_id}")
        
        target_hwnd = None
        
        def enum_windows_proc(hwnd, lParam):
            if not self.user32.IsWindowVisible(hwnd): return 1
            
            pid = c_long()
            self.user32.GetWindowThreadProcessId(hwnd, byref(pid))
            
            name = self.get_process_name(pid.value)
            
            # Heuristic: Check if process name is inside AppID or vice versa
            # e.g. "Spotify" in "Spotify.exe"
            match = False
            if name and app_id:
                n = name.lower().replace(".exe", "")
                a = app_id.lower()
                if n in a or a in n:
                    match = True
            
            if match:
                # Found a potential match
                # Check for window title to avoid focusing hidden/background helpers
                length = self.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                     nonlocal target_hwnd
                     target_hwnd = hwnd
                     return 0 # Stop enumeration
            return 1

        proc = self.WNDENUMPROC(enum_windows_proc)
        self.user32.EnumWindows(proc, 0)
        
        if target_hwnd:
            print(f"DEBUG: Found window {target_hwnd}, forcing foreground.")
            # Force foreground (classic trick: attach input)
            current_tid = self.kernel32.GetCurrentThreadId()
            target_tid = self.user32.GetWindowThreadProcessId(target_hwnd, 0)
            
            self.user32.AttachThreadInput(current_tid, target_tid, True)
            self.user32.ShowWindow(target_hwnd, self.SW_RESTORE)
            self.user32.SetForegroundWindow(target_hwnd)
            self.user32.AttachThreadInput(current_tid, target_tid, False)
            return True
        print("DEBUG: No matching window found.")
        return False


# --- Keyboard Input for Volume ---
class KEYBDINPUT(Structure):
    _fields_ = [("wVk", c_short),
                ("wScan", c_short),
                ("dwFlags", c_long),
                ("time", c_long),
                ("dwExtraInfo", c_long)]

class MOUSEINPUT(Structure):
    _fields_ = [("dx", c_long),
                ("dy", c_long),
                ("mouseData", c_long),
                ("dwFlags", c_long),
                ("time", c_long),
                ("dwExtraInfo", c_long)]

class HARDWAREINPUT(Structure):
    _fields_ = [("uMsg", c_long),
                ("wParamL", c_short),
                ("wParamH", c_short)]

class INPUT_I(Union):
    _fields_ = [("ki", KEYBDINPUT),
                ("mi", MOUSEINPUT),
                ("hi", HARDWAREINPUT)]

class INPUT(Structure):
    _fields_ = [("type", c_long),
                ("ii", INPUT_I)]

def send_volume_key(vk):
    # VK_VOLUME_MUTE = 0xAD, VK_VOLUME_DOWN = 0xAE, VK_VOLUME_UP = 0xAF
    # KEYEVENTF_KEYUP = 0x0002
    extra = windll.kernel32.GetMessageExtraInfo()
    ii_ = INPUT_I()
    ii_.ki = KEYBDINPUT(vk, 0x48, 0, 0, extra)
    x = INPUT(1, ii_)
    windll.user32.SendInput(1, byref(x), sizeof(x))
    
    ii_.ki = KEYBDINPUT(vk, 0x48, 2, 0, extra) # Hardware scancode for volume keys isn't strictly needed but good practice
    x = INPUT(1, ii_)
    windll.user32.SendInput(1, byref(x), sizeof(x))


# --- Helper: Rounded Rectangle ---
def get_rounded_rect_points(x1, y1, x2, y2, radius=25):
    points = []
    # Increase precision for mathematically round corners
    steps = 10 # Increase for more smoothness
    # Top Left
    for i in range(180, 271, steps):
        ang = math.radians(i)
        points.extend([x1+radius + radius*math.cos(ang), y1+radius + radius*math.sin(ang)])
    # Top Right
    for i in range(270, 361, steps):
        ang = math.radians(i)
        points.extend([x2-radius + radius*math.cos(ang), y1+radius + radius*math.sin(ang)])
    # Bottom Right
    for i in range(0, 91, steps):
        ang = math.radians(i)
        points.extend([x2-radius + radius*math.cos(ang), y2-radius + radius*math.sin(ang)])
    # Bottom Left
    for i in range(90, 181, steps):
        ang = math.radians(i)
        points.extend([x1+radius + radius*math.cos(ang), y2-radius + radius*math.sin(ang)])
        
    return points

def create_rounded_rect(canvas, x1, y1, x2, y2, radius=25, **kwargs):
    points = get_rounded_rect_points(x1, y1, x2, y2, radius)
    return canvas.create_polygon(points, **kwargs, smooth=True) 

# --- Helper: Rounded Image ---
def make_rounded_image(pil_img, width, height, radius=0):
    pil_img = pil_img.resize((int(width), int(height)), Image.Resampling.LANCZOS)
    mask = Image.new("L", (int(width), int(height)), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, int(width), int(height)), radius=radius, fill=255)
    output = Image.new("RGBA", (int(width), int(height)), (0, 0, 0, 0))
    output.paste(pil_img, (0, 0), mask)
    return output

# --- Themes Definition ---
THEMES = {
    "Dark Mode": {
        "bg_color": "#000000",
        "fg_color": "#FFFFFF",
        "sub_color": "#B0B0B0", # Lightened for visibility on Ambilight
        "accent_color": "#FFFFFF",
        "show_art": True,
        "show_timeline": True,
        "acrylic_tint": "#000000"
    },
    "Light Mode": {
        "bg_color": "#F0F0F0",
        "fg_color": "#111111",
        "sub_color": "#666666",
        "accent_color": "#111111",
        "show_art": True,
        "show_timeline": True,
        "acrylic_tint": "#FFFFFF"
    }
}

# --- Premium Modern Menu ---
class ModernMenu(tk.Toplevel):
    def __init__(self, parent, title="", width=240):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#0D0D0D")
        self.width = width
        self.items = []
        self.item_height = 42
        self.parent = parent
        self.visible = False
        
        # Native Windows 11 Effects (Shadow + Rounding)
        try:
            hwnd = windll.user32.GetParent(self.winfo_id())
            # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, byref(c_long(2)), sizeof(c_long))
            # DWMWA_BORDER_COLOR = 34 (ColorRef: 0x00BBGGRR) -> Dark Grey Border
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, byref(c_long(0x00404040)), sizeof(c_long)) 
            # DWMWA_CAPTION_COLOR = 35 -> Match bg
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(c_long(0x000D0D0D)), sizeof(c_long))
        except:
            pass
            
        self.canvas = tk.Canvas(self, width=self.width, height=1, bg="#0D0D0D", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.bind("<FocusOut>", lambda e: self.hide())
        
    def add_item(self, label, command=None, icon=None, is_header=False):
        self.items.append({
            "label": label,
            "command": command,
            "icon": icon,
            "is_header": is_header,
            "id": None,
            "text_id": None,
            "icon_id": None
        })
        self.refresh_height()

    def add_separator(self):
        self.items.append({"label": "---", "is_separator": True})
        self.refresh_height()

    def refresh_height(self):
        h = 0
        for item in self.items:
            if item.get("is_separator"): h += 12
            elif item.get("is_header"): h += 30
            else: h += self.item_height
        self.total_height = h + 20 # Padding
        self.canvas.config(height=self.total_height)
        self.geometry(f"{self.width}x{self.total_height}")

    def draw(self):
        self.canvas.delete("all")
        # Native DWM handles the background shape now
        
        curr_y = 10
        for i, item in enumerate(self.items):
            if item.get("is_separator"):
                self.canvas.create_line(15, curr_y + 6, self.width-15, curr_y + 6, fill="#2A2A2A", width=1)
                curr_y += 12
                continue
                
            if item.get("is_header"):
                self.canvas.create_text(20, curr_y + 15, text=item["label"].upper(), anchor=tk.W, fill="#666666", font=("Segoe UI Variable Display", 8, "bold"))
                curr_y += 30
                continue
            
            # Draw item
            tag = f"item_{i}"
            rect = create_rounded_rect(self.canvas, 8, curr_y, self.width-8, curr_y + self.item_height, radius=12, fill="#0D0D0D", outline="", tags=tag)
            
            icon_x = 22
            if item["icon"]:
                self.canvas.create_text(icon_x, curr_y + self.item_height/2, text=item["icon"], fill="#FFFFFF", font=("Segoe UI Symbol", 11), tags=tag)
                text_x = 48
            else:
                text_x = 22
                
            self.canvas.create_text(text_x, curr_y + self.item_height/2, text=item["label"], anchor=tk.W, fill="#E8E8E8", font=("Segoe UI Variable Display", 10), tags=tag)
            
            # Hover effects
            def on_enter(e, t=tag, r=rect):
                self.canvas.itemconfig(r, fill="#1F1F1F")
            def on_leave(e, t=tag, r=rect):
                self.canvas.itemconfig(r, fill="#0D0D0D")
            def on_click(e, cmd=item["command"]):
                self.hide()
                if cmd: cmd()
                
            self.canvas.tag_bind(tag, "<Enter>", on_enter)
            self.canvas.tag_bind(tag, "<Leave>", on_leave)
            self.canvas.tag_bind(tag, "<Button-1>", on_click)
            
            curr_y += self.item_height

    def show(self, x, y):
        self.draw()
        # Prevent going off screen
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        if x + self.width > screen_w: x -= self.width
        if y + self.total_height > screen_h: y -= self.total_height
        
        self.geometry(f"+{int(x)}+{int(y)}")
        self.deiconify()
        self.focus_set()
        self.visible = True
        
        # Track state on parent WIDGET
        self.parent.ctx_menu_open = True

    def hide(self):
        self.withdraw()
        self.visible = False
        self.parent.ctx_menu_open = False

# --- Widget Class ---
class MediaWidget(tk.Tk):
    def __init__(self):
        super().__init__()
        print("\n" + "="*40)
        print(" PHONON INITIALIZING (LOGGING ACTIVE)")
        print("="*40 + "\n")
        self.title("Phonon")
        
        # Theme State
        self.current_theme_name = "Dark Mode"
        self.width = 510
        self.height = 130
        self.border_radius = 27
        self.island_color = "#000000"
        self.fg_color = "#FFFFFF"
        self.sub_color = "#AAAAAA"
        
        # Mode & Docking
        self.mode = "island" # 'island' or 'normal'
        self.dock_side = "top" # 'top', 'left', 'right'
        self.normal_geometry = "334x100+4+-10"
        self.island_width = 510
        self.island_height = 130
        self.island_border_radius = 27
        self.normal_border_radius = 29
        
        # Default Toggles
        self.show_title = True
        self.show_artist = True
        self.show_progress = True
        self.show_controls = True
        self.sticky = False
        self.dynamic_island_enabled = True
        
        # Load Config
        self.load_config()
        
        self.bg_key = "#000001"
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        self.attributes('-transparentcolor', self.bg_key)
        self.configure(bg=self.bg_key)
        
        # Apply Windows Effects
        self.update_idletasks()
        self.apply_acrylic_effect(self.winfo_id(), THEMES[self.current_theme_name]["acrylic_tint"])
        
        # System Tray Setup
        self.setup_system_tray()
        self.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        
        # Customization from config
        self.animation_speed = 0.44
        self.auto_hide_delay = 250
        self.stiffness = 410
        self.damping = 49
        self.ambilight_enabled = True
        self.ambilight_intensity = 0.95
        self.hover_zone_height = 14
        self.lip_size = 9
        self.y_offset = 7
        self.x_offset = 10 # Default
        
        # State
        self.session = None
        self.running = True
        self.dragging_slider = False
        self.dragging_window = False
        self.resizing_window = False
        self.resize_edge = None 
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.win_start_x = 0
        self.win_start_y = 0
        self.win_start_w = 0
        self.win_start_h = 0
        self.can_seek = False 
        self.sticky = False
        self.ctx_menu_open = False
        
        # Session Hold Time (prevent rapid switching)
        self.last_session_id = None
        self.last_session_priority = -1
        self.last_session_lock_time = 0
        self.session_hold_duration = 0.5  # 500ms hold time
        
        # Content Hold Time (prevent "No Media" flash)
        self.last_media_time = 0  # Last time we had valid media
        self.content_hold_duration = 5.0  # Keep showing old content for 5s when no session
        
        # Gesture Tracking State
        self.gesture_start_x = 0
        self.gesture_start_time = 0
        self.gesture_triggered = False
        self.mouse_leave_time = 0
        
        # State Cache
        self.last_track_key = None
        self.last_ratio = 0
        self.last_status = 5 # Stopped/No Media
        
        # Tooltip State
        self.tooltip_win = None
        self.tooltip_job = None
        self.tooltip_text = ""
        self.fade_jobs = {}
        self.title_dy = 0
        self.artist_dy = 0
        
        # Initial Velocities for Spring Physics
        self.vel_x = 0.0
        self.vel_y = 0.0
        self.vel_w = 0.0
        self.vel_h = 0.0
        
        # Dimension State (Actual current values)
        self.setup_dimensions()
        
        # UI Setup
        self.setup_ui()
        
        # Loop Setup
        self.attributes('-alpha', 1.0)
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.run_async_loop, daemon=True)
        self.thread.start()
        
        # Periodic
        self.after(16, self.animate_physics) 
        self.after(30, self.check_mouse)
        self.last_config_mtime = 0
        self.check_config_reload()

    def setup_dimensions(self, reset_physics=True):
        screen_w = self.winfo_screenwidth()
        
        if self.mode == "island":
            self.dock_side = "top"
            self.width = self.island_width
            self.height = self.island_height
            
            self.x_pos = (screen_w - self.width) // 2
            
            if getattr(self, 'dynamic_island_enabled', False):
                 self.y_visible = 0 
                 self.y_hidden = -self.height + self.lip_size
            else:
                 self.y_hidden = -self.height + self.lip_size
                 self.y_visible = self.y_offset
                
            if reset_physics:
                self.current_x = self.x_pos
                self.current_y = self.y_hidden
                self.target_x = self.x_pos
                self.target_y = self.y_hidden
                self.current_width = self.width
                self.current_height = self.height
            
            # target_x/y for island are updated by check_mouse, 
            # but we set them here initially
            if reset_physics:
                self.target_y = self.y_hidden
            
            self.update_dock_side()
        else:
            # Normal Mode: Autoritative parsing of geometry string
            try:
                # Format: WxH+X+Y
                parts = self.normal_geometry.replace('x', '+').split('+')
                w, h = int(parts[0]), int(parts[1])
                x, y = int(parts[2]), int(parts[3])
                
                self.width, self.height = w, h
                if reset_physics:
                    self.current_x, self.current_y = x, y
                    self.current_width, self.current_height = w, h
                
                # URGENT: Always update targets in Normal Mode so config changes move the window
                self.target_x, self.target_y = x, y
            except Exception as e:
                print(f"DEBUG: Geometry Parse Error {e}. Resetting to default.")
                if reset_physics:
                    self.current_x, self.current_y = 100, 100
                    self.current_width, self.current_height = 500, 125
                self.width, self.height = 500, 125
                self.target_x, self.target_y = 100, 100
            
            self.update_dock_side()
        
        # Immediate sync for mode-snapping
        self.geometry(f"{int(self.width)}x{int(self.height)}+{int(self.current_x)}+{int(self.current_y)}")

    def update_dock_side(self):
        screen_w = self.winfo_screenwidth()
        # Snapping thresholds
        snap = 30
        if self.current_y <= snap: 
            self.dock_side = "top"
            self.y_hidden = -self.height + self.lip_size
            self.y_visible = self.y_offset
        elif self.current_x <= snap: 
            self.dock_side = "left"
            self.x_hidden = -self.width + self.lip_size
            self.x_visible = self.x_offset
        elif self.current_x + self.width >= screen_w - snap: 
            self.dock_side = "right"
            self.x_hidden = screen_w - self.lip_size
            self.x_visible = screen_w - self.width - self.x_offset
        else: 
            self.dock_side = None

    def check_config_reload(self):
        try:
             # Very simple polling
            config_path = "config.json"
            if os.path.exists(config_path):
                mtime = os.path.getmtime(config_path)
                if self.last_config_mtime == 0:
                    self.last_config_mtime = mtime
                elif mtime > self.last_config_mtime:
                     # Allow write to settle
                    time.sleep(0.05)
                    print("Settings changed. Reloading...")
                    self.last_config_mtime = mtime
                    self.load_config()
                    self.apply_config_changes()
        except Exception as e:
            print(f"CRITICAL RELOAD ERROR: {e}")
            pass
        self.after(100, self.check_config_reload)

    def apply_config_changes(self):
        self.deiconify() 
        self.update_idletasks() 
        
        # CRITICAL: Preserve mode-specific dimensions before setup_dimensions
        # This prevents cross-contamination when settings change
        if self.mode == "island":
            # Ensure we're using the island-specific values
            self.width = self.island_width
            self.height = self.island_height
            self.border_radius = self.island_border_radius
        else:
            # Parse normal geometry to get width/height
            try:
                dims = self.normal_geometry.split('+')[0]
                self.width, self.height = map(int, dims.split('x'))
            except:
                pass
            self.border_radius = self.normal_border_radius
        
        self.setup_dimensions(reset_physics=False)
        
        # Invalidate art cache to force redraw on setting change
        self.last_drawn_size = -1
        self.last_drawn_w = -1
        
        self.setup_ui()
        
        # Trigger immediate background update if Ambilight state might have changed
        if hasattr(self, 'last_pil_img') and self.ambilight_enabled:
             # Force re-process
             self.run_task(lambda: self.async_process_background(self.last_pil_img, self.width, self.height, self.border_radius))
        elif not self.ambilight_enabled:
             self.apply_glow_bg(None)

        self.apply_acrylic_effect(self.winfo_id(), THEMES[self.current_theme_name]["acrylic_tint"])

    def apply_acrylic_effect(self, hwnd, color="#000000"):
        """Applies Mica on Windows 11 and Acrylic on Windows 10."""
        try:
            # Constants for DWM
            DWMWA_SYSTEMBACKDROP_TYPE = 38
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            
            DWMSBT_DISABLE = 1
            DWMSBT_MAINWINDOW = 2      # Mica
            DWMSBT_TRANSIENTWINDOW = 3 # Acrylic
            DWMSBT_TABBEDWINDOW = 4    # Tabbed (Mica Alt)

            # Check Windows version
            win_version = sys.getwindowsversion()
            is_win11 = win_version.build >= 22000

            # Set Dark Mode preference if needed
            dark_mode = 1 if "Light" not in self.current_theme_name else 0
            windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(ctypes.c_int(dark_mode)), 4)

            if is_win11:
                # Windows 11 uses Mica or Acrylic via DWMWA_SYSTEMBACKDROP_TYPE
                backdrop = DWMSBT_TRANSIENTWINDOW if "Light" not in self.current_theme_name else DWMSBT_MAINWINDOW
                windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, byref(ctypes.c_int(backdrop)), 4)
            else:
                # Windows 10 Acrylic workaround using SetWindowCompositionAttribute (simplified check)
                # For Phase 1 we use a simpler fallback if DWMWA_SYSTEMBACKDROP doesn't exist (< Win 11)
                # But we attempt the attribute call anyway just in case of variations
                windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, byref(ctypes.c_int(DWMSBT_TRANSIENTWINDOW)), 4)
            
            # Set background to clear/semi-trans to let DWM show through
            # We use an extremely dark tint to anchor the blur
            self.configure(bg=self.bg_key)
            if hasattr(self, 'canvas'):
                self.canvas.configure(bg=self.bg_key)
                
        except Exception as e:
            print(f"DWM Effect Error: {e}")
            # Fallback to Solid Black as requested
            self.island_color = "#000000"
            if hasattr(self, 'canvas'):
                self.canvas.configure(bg="#000000")

    def load_config(self):
        config_path = "config.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    self.mode = config.get("mode", self.mode)
                    self.normal_geometry = config.get("normal_geometry", self.normal_geometry)
                    
                    # A_B Isolation: Island Mode Dims
                    self.island_width = config.get("island_width", self.island_width)
                    self.island_height = config.get("island_height", self.island_height)
                    self.island_border_radius = config.get("island_border_radius", self.island_border_radius)
                    
                    # A_B Isolation: Normal Mode Dims
                    self.normal_border_radius = config.get("normal_border_radius", self.normal_border_radius)
                    
                    # Set Active Radius for Startup
                    self.border_radius = self.island_border_radius if self.mode == "island" else self.normal_border_radius
                    
                    # Apply specific mode geometry
                    if self.mode == "island":
                        self.width = self.island_width
                        self.height = self.island_height
                    else:
                        try:
                            # Extract WxH from normal_geometry (WxH+X+Y)
                            dims = self.normal_geometry.split('+')[0]
                            self.width, self.height = map(int, dims.split('x'))
                        except:
                            pass
                    
                    # Toggles
                    self.show_title = config.get("show_title", self.show_title)
                    self.show_artist = config.get("show_artist", self.show_artist)
                    self.show_progress = config.get("show_progress", self.show_progress)
                    self.show_controls = config.get("show_controls", self.show_controls)
                    self.dynamic_island_enabled = config.get("dynamic_island_enabled", self.dynamic_island_enabled)
                    self.ambilight_enabled = config.get("ambilight_enabled", self.ambilight_enabled)
                    self.ambilight_intensity = config.get("ambilight_intensity", self.ambilight_intensity * 100) / 100.0
                    
                    # Behavior
                    self.animation_speed = config.get("animation_speed", self.animation_speed)
                    inter_cfg = config.get("interaction", {})
                    self.hover_zone_height = inter_cfg.get("hover_zone_height", self.hover_zone_height)
                    self.auto_hide_delay = config.get("auto_hide_delay", self.auto_hide_delay)
                    
                    # Offsets
                    self.lip_size = inter_cfg.get("lip_size", self.lip_size)
                    self.y_offset = inter_cfg.get("y_offset", self.y_offset)
                    self.x_offset = inter_cfg.get("x_offset", self.x_offset)
                    
                    # Spring Physics
                    self.stiffness = config.get("stiffness", self.stiffness)
                    self.damping = config.get("damping", self.damping)
                    
                    theme_cfg = config.get("theme", {})
                    self.island_color = theme_cfg.get("bg_color", self.island_color)
                    self.fg_color = theme_cfg.get("fg_color", self.fg_color)
                    self.current_theme_name = config.get("theme_name", self.current_theme_name)
                    
                    print("Config loaded and applied.")
            except Exception as e:
                print(f"Error loading config: {e}")
        else:
            print("Config file not found, using defaults.")

    def save_config(self):
        config_path = "config.json"
        data = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    data = json.load(f)
            except: pass
        
        # CRITICAL: Update ONLY the keys for the current mode
        if self.mode == "island":
            self.island_width = self.width
            self.island_height = self.height
            self.island_border_radius = self.border_radius
            data["island_width"] = self.island_width
            data["island_height"] = self.island_height
            data["island_border_radius"] = self.island_border_radius
        else:
            self.normal_geometry = f"{int(self.width)}x{int(self.height)}+{int(self.current_x)}+{int(self.current_y)}"
            self.normal_border_radius = self.border_radius
            data["normal_geometry"] = self.normal_geometry
            data["normal_border_radius"] = self.normal_border_radius

        # Global settings (not mode-specific)
        data["mode"] = self.mode
        data["ambilight_enabled"] = self.ambilight_enabled
        data["show_title"] = self.show_title
        data["show_artist"] = self.show_artist
        data["show_progress"] = self.show_progress
        data["show_controls"] = self.show_controls
        
        # REMOVE legacy keys if they exist to prevent pollution
        if "width" in data:
            del data["width"]
        if "height" in data:
            del data["height"]
        if "border_radius" in data:
            del data["border_radius"]
            
        try:
            with open(config_path, "w") as f:
                data["theme_name"] = self.current_theme_name
                json.dump(data, f, indent=4)
            # Update last mtime to prevent immediate redundant reload
            self.last_config_mtime = os.path.getmtime(config_path)
        except Exception as e:
            print(f"Error saving config: {e}")

    def toggle_mode(self):
        # 1. Save EXITING mode dimensions to storage variables
        if self.mode == "island":
            self.island_width = self.width
            self.island_height = self.height
            self.island_border_radius = self.border_radius
        else:
            self.normal_geometry = f"{int(self.width)}x{int(self.height)}+{int(self.current_x)}+{int(self.current_y)}"
            self.normal_border_radius = self.border_radius
        
        # 2. Switch the mode flag
        self.mode = "normal" if self.mode == "island" else "island"
        
        # 3. CRITICAL: Load NEW mode dimensions BEFORE setup_dimensions
        #    This prevents the old mode's dimensions from contaminating the new mode
        if self.mode == "island":
            self.width = self.island_width
            self.height = self.island_height
            self.border_radius = self.island_border_radius
        else:
            # Parse normal geometry to extract width, height, AND position
            try:
                parts = self.normal_geometry.replace('x', '+').split('+')
                self.width, self.height = int(parts[0]), int(parts[1])
                self.current_x, self.current_y = int(parts[2]), int(parts[3])
                self.target_x, self.target_y = self.current_x, self.current_y
            except:
                self.width, self.height = 500, 125
                self.current_x, self.current_y = 100, 100
                self.target_x, self.target_y = 100, 100
            self.border_radius = self.normal_border_radius
        
        # 4. Save state (including the new mode flag)
        self.save_config()
        
        # 5. RESTART the widget for clean initialization
        #    This prevents visual glitches with border radius and ensures proper layout
        self.running = False
        
        # Release mutex before restarting
        if hasattr(self, '_app_mutex') and self._app_mutex:
            windll.kernel32.ReleaseMutex(self._app_mutex)
            windll.kernel32.CloseHandle(self._app_mutex)
        
        self.destroy()
        subprocess.Popen([sys.executable, "widget.py"], cwd=os.getcwd())

    def setup_ui(self):
        if not hasattr(self, 'canvas'):
            self.canvas = tk.Canvas(self, bg=self.bg_key, highlightthickness=0)
            self.canvas.pack(fill=tk.BOTH, expand=True)
            self.canvas.bind("<Button-1>", self.on_click)
            self.canvas.bind("<B1-Motion>", self.on_drag)
            self.canvas.bind("<ButtonRelease-1>", self.on_release)
            self.canvas.bind("<Motion>", self.on_mouse_move)
            self.canvas.bind("<MouseWheel>", self.on_scroll)
            self.canvas.bind("<Shift-MouseWheel>", self.on_scroll)

        
        self.canvas.delete("all")
        # ═══════════════════════════════════════════════════════════
        # ULTRA PREMIUM MODERN POPUP MENU
        # ═══════════════════════════════════════════════════════════
        def show_ctx(e):
            m = ModernMenu(self, width=240)
            
            # Status Section
            status_icon = "📌" if self.sticky else "📍"
            m.add_item(f"{status_icon} Stay Visible", self.toggle_sticky)
            
            mode_icon = "🔄"
            mode_label = "Switch to Normal" if self.mode == "island" else "Switch to Island"
            m.add_item(f"{mode_icon} {mode_label}", self.toggle_mode)
            
            m.add_separator()
            
            # Appearance Section
            ambi_label = "✨ Disable Ambilight" if self.ambilight_enabled else "✨ Enable Ambilight"
            m.add_item(ambi_label, self.toggle_ambilight)
            
            # Simplified theme/speed as direct items since submenu is complex for custom canvas
            m.add_item("🎨 Switch Theme", lambda: self.apply_theme("Light Mode" if self.current_theme_name == "Dark Mode" else "Dark Mode"))
            
            m.add_separator()
            
            m.add_item("⚙️ Settings", self.launch_settings)
            m.add_item("🔄 Reload Config", self.apply_config_changes)
            
            m.add_separator()
            
            m.add_item("🔁 Restart App", self.restart_app)
            m.add_item("❌ Exit", self.quit_app)
            
            m.show(e.x_root, e.y_root)

        self.canvas.bind("<Button-3>", show_ctx) # Right Click
        
        # Background (Image based now)
        self.bg_img_id = self.canvas.create_image(self.width/2, self.height/2, anchor=tk.CENTER)
        self.bg_id = create_rounded_rect(self.canvas, 0, 0, self.width, self.height, radius=self.border_radius, fill=self.island_color)
        # We keep bg_id as a fallback/base layer
        
        # --- Fix for Mode Switch: Invalidate Play/Pause IDs ---
        # Since we just cleared the canvas, these IDs are dead. 
        # By removing the attributes, update_play_pause_ui will recreate them.
        if hasattr(self, 'pause_id_1'): del self.pause_id_1
        if hasattr(self, 'pause_id_2'): del self.pause_id_2
        if hasattr(self, 'play_id'): del self.play_id
        
        # --- Fix for Mode Switch: Restore Glow ---
        # If we have a glow image ready, apply it immediately to the new bg_img_id
        if hasattr(self, 'tk_glow_bg') and self.tk_glow_bg:
            self.canvas.itemconfig(self.bg_img_id, image=self.tk_glow_bg)
            self.canvas.itemconfig(self.bg_id, state="hidden")

        # --- Fix for Album Art: Force Redraw ---
        self.last_drawn_size = -1
        self.last_drawn_w = -1


        
        # Scale fonts based on height
        base_h = 125
        scale = self.height / base_h
        padding = max(10, self.height * 0.12)
        
        # Album Art Positioning
        self.art_size = int(self.height - (padding * 2.2))
        self.art_x = padding + self.art_size // 2 
        self.art_y = self.height // 2
        
        # Calculate Text Center (Evenly spaced between art and right border)
        right_margin = 35
        art_end_x = padding + self.art_size + right_margin
        text_x = art_end_x + (self.width - art_end_x - right_margin) // 2
        
        # Text Styles
        from tkinter import font as tkfont
        self.font_title = tkfont.Font(family="Segoe UI Variable Display", size=int(13 * scale), weight="bold")
        self.font_artist = tkfont.Font(family="Segoe UI Variable Text", size=int(9 * scale), weight="normal")
        self.font_time = tkfont.Font(family="Segoe UI Variable Text", size=int(9 * scale), weight="bold")
        self.artist_fg = "#909090"
        
        # Vertical stack center values
        if self.show_progress and self.show_controls:
            title_y = self.height * 0.22
            artist_y = self.height * 0.40
            ctrl_y = self.height * 0.64
            self.bar_y = self.height * 0.86
        elif self.show_progress:
            title_y = self.height * 0.35
            artist_y = self.height * 0.52
            self.bar_y = self.height * 0.85
            ctrl_y = -100
        elif self.show_controls:
            title_y = self.height * 0.32
            artist_y = self.height * 0.50
            ctrl_y = self.height * 0.75
            self.bar_y = -100
        else:
            title_y = self.height * 0.42
            artist_y = self.height * 0.60
            ctrl_y = -100
            self.bar_y = -100
            
        # Theme Overrides
        theme = THEMES[self.current_theme_name]
        self.island_color = theme["bg_color"]
        self.fg_color = theme["fg_color"]
        self.sub_color = theme["sub_color"]
        self.artist_fg = self.sub_color
        
        # Mode Specific Overrides
        if self.current_theme_name == "Minimalist":
            # No art, center everything
            text_x = self.width // 2
            self.show_progress = False # Override for minimalist
            self.bar_y = -100
            title_y = self.height * 0.45
            artist_y = self.height * 0.55
            ctrl_y = -100 # No controls in minimalist? Let's hide them.

        if self.show_title:
            # SHADOW: Softer color (#121212) and smaller offset for a more premium look
            self.title_shadow_id = self.canvas.create_text(text_x + 1, title_y + 1, text="", font=self.font_title, fill="#121212", anchor="center", tags="expanded_ui")
            self.title_id = self.canvas.create_text(text_x, title_y, text="Waiting...", font=self.font_title, fill=self.fg_color, anchor="center", tags="expanded_ui")
        else:
            self.title_id = self.canvas.create_text(-1000, -1000, text="", tags="expanded_ui")
            self.title_shadow_id = self.canvas.create_text(-1000, -1000, text="", tags="expanded_ui")
        
        if self.show_artist:
            # SHADOW: Softer color (#121212) and smaller offset
            self.artist_shadow_id = self.canvas.create_text(text_x + 0.8, artist_y + 0.8, text="", font=self.font_artist, fill="#121212", anchor="center", tags="expanded_ui")
            self.artist_id = self.canvas.create_text(text_x, artist_y, text="-", font=self.font_artist, fill=self.artist_fg, anchor="center", tags="expanded_ui")
        else:
            self.artist_id = self.canvas.create_text(-1000, -1000, text="", tags="expanded_ui")
            self.artist_shadow_id = self.canvas.create_text(-1000, -1000, text="", tags="expanded_ui")

        # Time Labels and Bar
        if self.show_progress:
            # Center bar in the available text space
            bar_w = (self.width - art_end_x - right_margin) * 0.75 # Use 75% of available space
            bar_w_half = bar_w // 2
            
            bar_x1 = text_x - bar_w_half
            bar_x2 = text_x + bar_w_half
            self.bar_coords = (bar_x1, self.bar_y, bar_x2, self.bar_y)
            
            self.lbl_curr_time_shadow = self.canvas.create_text(bar_x1 - (10 * scale) + 0.5, self.bar_y + 0.5, text="0:00", font=self.font_time, fill="#121212", anchor="e", tags="expanded_ui")
            self.lbl_curr_time = self.canvas.create_text(bar_x1 - (10 * scale), self.bar_y, text="0:00", font=self.font_time, fill=self.fg_color, anchor="e", tags="expanded_ui")
            
            self.lbl_total_time_shadow = self.canvas.create_text(bar_x2 + (10 * scale) + 0.5, self.bar_y + 0.5, text="0:00", font=self.font_time, fill="#121212", anchor="w", tags="expanded_ui")
            self.lbl_total_time = self.canvas.create_text(bar_x2 + (10 * scale), self.bar_y, text="0:00", font=self.font_time, fill=self.fg_color, anchor="w", tags="expanded_ui")

            # Thicker bar (4px)
            bar_thick = int(4 * scale)
            self.bar_bg_id = self.canvas.create_line(bar_x1, self.bar_y, bar_x2, self.bar_y, width=bar_thick, fill="#222222", capstyle=tk.ROUND, tags="expanded_ui")
            self.bar_val_id = self.canvas.create_line(bar_x1, self.bar_y, bar_x1, self.bar_y, width=bar_thick, fill=self.fg_color, capstyle=tk.ROUND, tags="expanded_ui")
            
            dot_r = 5.0 * scale
            self.dot_id = self.canvas.create_oval(bar_x1-dot_r, self.bar_y-dot_r, bar_x1+dot_r, self.bar_y+dot_r, fill=self.fg_color, outline="", tags="expanded_ui")
            self.seek_hitbox = (bar_x1-20, self.bar_y-20, bar_x2+20, self.bar_y+20)
        else:
            self.lbl_curr_time = self.canvas.create_text(-100, -100, text="", tags="expanded_ui")
            self.lbl_total_time = self.canvas.create_text(-100, -100, text="", tags="expanded_ui")
            self.bar_coords = (0,0,0,0)
            self.bar_val_id = self.canvas.create_line(0,0,0,0, tags="expanded_ui")
            self.dot_id = self.canvas.create_oval(0,0,0,0, tags="expanded_ui")
            self.seek_hitbox = (0,0,0,0)

        if self.show_controls:
            btn_offset = 48 * scale 
            
            s = 9 * scale 
            gap_tri = 0.5 * scale
            self.canvas.create_polygon(text_x - btn_offset, ctrl_y - s, text_x - btn_offset, ctrl_y + s, text_x - btn_offset - s, ctrl_y, fill=self.fg_color, outline=self.fg_color, width=1, joinstyle=tk.ROUND, tags=("btn_prev", "expanded_ui"))
            self.canvas.create_polygon(text_x - btn_offset + s + gap_tri, ctrl_y - s, text_x - btn_offset + s + gap_tri, ctrl_y + s, text_x - btn_offset + gap_tri, ctrl_y, fill=self.fg_color, outline=self.fg_color, width=1, joinstyle=tk.ROUND, tags=("btn_prev", "expanded_ui"))
            
            self.btn_play_id = self.canvas.create_text(text_x, ctrl_y, text="", font=("Arial", 0), tags=("btn_play", "expanded_ui"))
            
            self.canvas.create_polygon(text_x + btn_offset, ctrl_y - s, text_x + btn_offset, ctrl_y + s, text_x + btn_offset + s, ctrl_y, fill=self.fg_color, outline=self.fg_color, width=1, joinstyle=tk.ROUND, tags=("btn_next", "expanded_ui"))
            self.canvas.create_polygon(text_x + btn_offset - s - gap_tri, ctrl_y - s, text_x + btn_offset - s - gap_tri, ctrl_y + s, text_x + btn_offset - gap_tri, ctrl_y, fill=self.fg_color, outline=self.fg_color, width=1, joinstyle=tk.ROUND, tags=("btn_next", "expanded_ui"))
            
            self.update_play_pause_ui(4) 
            
            for tag in ["btn_prev", "btn_play", "btn_next"]:
                self.canvas.tag_bind(tag, "<Enter>", lambda e: self.canvas.config(cursor="hand2"))
                self.canvas.tag_bind(tag, "<Leave>", lambda e: self.canvas.config(cursor=""))
        else:
            self.btn_prev_id = None
            self.btn_play_id = None
            self.btn_next_id = None


        # Album Art Image
        self.art_id = self.canvas.create_image(self.art_x, self.art_y, anchor=tk.CENTER, tags=("art", "art_group"))
        if not hasattr(self, 'last_pil_img'):
             self.canvas.itemconfig(self.art_id, state="hidden")
            
        self.canvas.tag_bind("art", "<Enter>", lambda e: self.canvas.config(cursor="hand2"))
        self.canvas.tag_bind("art", "<Leave>", lambda e: self.canvas.config(cursor=""))
        self.canvas.tag_bind("art", "<Button-1>", lambda e: self.run_task(self.focus_source_app))

        # Apply visibility based on theme
        if not theme["show_art"]:
            self.canvas.itemconfig("art_group", state="hidden")
        if not theme["show_timeline"]:
            self.canvas.itemconfig("expanded_ui", state="hidden")
            # But keep title/artist visible if they were supposed to be
            if self.show_title: self.canvas.itemconfig(self.title_id, state="normal")
            if self.show_artist: self.canvas.itemconfig(self.artist_id, state="normal")
            # Hide the others
            if hasattr(self, 'bar_bg_id'): self.canvas.itemconfig(self.bar_bg_id, state="hidden")
            if hasattr(self, 'bar_val_id'): self.canvas.itemconfig(self.bar_val_id, state="hidden")
            if hasattr(self, 'dot_id'): self.canvas.itemconfig(self.dot_id, state="hidden")
            if hasattr(self, 'lbl_curr_time'): self.canvas.itemconfig(self.lbl_curr_time, state="hidden")
            if hasattr(self, 'lbl_total_time'): self.canvas.itemconfig(self.lbl_total_time, state="hidden")

        
        # Resize Handle
        if self.mode == "normal":
            self.canvas.create_rectangle(self.width-30, self.height-30, self.width, self.height, fill="", outline="", tags="resize_handle")
            self.canvas.tag_bind("resize_handle", "<Enter>", lambda e: self.canvas.config(cursor="size_nw_se"))
            self.canvas.tag_bind("resize_handle", "<Leave>", lambda e: self.canvas.config(cursor=""))



    # --- Interaction ---
    def on_click(self, event):
        x, y = event.x, event.y
        self.drag_start_x = event.x_root
        self.drag_start_y = event.y_root
        self.win_start_x = self.winfo_x()
        self.win_start_y = self.winfo_y()
        self.win_start_w = self.current_width
        self.win_start_h = self.height
        
        print("\n" + "*"*30)
        print(f" WIDGET CLICKED AT: {x}, {y}")
        print("*"*30)
        sys.stdout.flush()

        # 1. Interactive Elements (Priority)
        # Using a 30x30 bounding area
        items = self.canvas.find_overlapping(x-15, y-15, x+15, y+15)
        # Also include the absolute CLOSEST item for thin icons
        closest = self.canvas.find_closest(x, y, halo=5)
        all_items = set(list(items) + list(closest))
        
        print(f"   Items found: {all_items}")
        sys.stdout.flush()
        
        for i in all_items:
            tags = self.canvas.gettags(i)
            print(f"   Checking Piece {i} with Tags: {tags}")
            sys.stdout.flush()
            
            if "btn_prev" in tags:
                self.run_task(self.svc_prev)
                self.pulse_btn(i)
                return
            elif "btn_next" in tags:
                self.run_task(self.svc_next)
                self.pulse_btn(i)
                return
            elif "btn_play" in tags:
                self.run_task(self.svc_play_pause)
                self.pulse_btn(i)
                return
            elif "art" in tags:
                self.run_task(self.focus_source_app)
                self.gesture_start_x = event.x_root
                self.gesture_start_time = time.time()
                self.gesture_triggered = False
                return
            elif "resize_handle" in tags:
                print("   [CLICK] Resize Handle Hit")
                self.resizing_window = True
                return

        # 2. Seek Bar (Secondary)
        if self.show_progress:
            sx1, sy1, sx2, sy2 = self.seek_hitbox
            if sx1 <= x <= sx2 and sy1 <= y <= sy2:
                print("   [CLICK] Seek Bar Hit")
                self.dragging_slider = True
                self.update_seek_visual(x)
                return

        # 3. Mode-specific Window Dragging
        if self.mode == "normal":
            print("   [CLICK] Window Drag Started")
            self.dragging_window = True
            return

        # 4. Background Toggles
        print("   [CLICK] Background - Toggling Sticky")
        self.toggle_sticky()

    def toggle_sticky(self, val=None):
        if val is not None:
            self.sticky = val
        elif hasattr(self, 'sticky_var'):
            self.sticky = self.sticky_var.get()
        else:
            self.sticky = not self.sticky
            
        if hasattr(self, 'sticky_var'):
            self.sticky_var.set(self.sticky)
            
        # Pulse background to show feedback (Premium Dark)
        current_color = self.island_color
        self.canvas.itemconfig(self.bg_id, fill="#0A0A0A" if self.sticky else self.island_color)
        if not self.sticky:
            self.after(200, lambda: self.canvas.itemconfig(self.bg_id, fill=current_color))

    def apply_theme(self, theme_name):
        self.current_theme_name = theme_name
        self.save_config()
        self.setup_ui()
        self.apply_acrylic_effect(self.winfo_id(), THEMES[theme_name]["acrylic_tint"])
        # Trigger an immediate media update to refresh colors
        if hasattr(self, 'last_track_key') and self.last_track_key:
            self.update_media_state(self.last_track_key[0], self.last_track_key[1], 0, 1, 0, None)
    
    # ═══════════════════════════════════════════════════════════
    # CONTEXT MENU HELPER METHODS
    # ═══════════════════════════════════════════════════════════
    
    def toggle_ambilight(self):
        """Toggle ambilight and restart widget for changes to apply"""
        self.ambilight_enabled = not self.ambilight_enabled
        self.save_config()
        # Restart to apply ambilight changes cleanly
        self.restart_app()
    
    def restart_app(self, icon=None, item=None):
        """Restart the widget application"""
        self.running = False
        
        if hasattr(self, 'tray_icon'):
            self.tray_icon.stop()
        
        # Release mutex before restarting
        if hasattr(self, '_app_mutex') and self._app_mutex:
            windll.kernel32.ReleaseMutex(self._app_mutex)
            windll.kernel32.CloseHandle(self._app_mutex)
        
        self.destroy()
        
        if getattr(sys, 'frozen', False):
            # Running as EXE
            subprocess.Popen([sys.executable], cwd=os.getcwd())
        else:
            # Running as script
            subprocess.Popen([sys.executable, "widget.py"], cwd=os.getcwd())

    # ═══════════════════════════════════════════════════════════
    # SYSTEM TRAY INTEGRATION
    # ═══════════════════════════════════════════════════════════
    def setup_system_tray(self):
        image = self.create_tray_icon()
        menu = pystray.Menu(
            pystray.MenuItem("Show Media Island", self.show_window),
            pystray.MenuItem("Restart", self.restart_app),
            pystray.MenuItem("Quit", self.quit_app)
        )
        self.tray_icon = pystray.Icon("MediaIsland", image, "Media Island", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def create_tray_icon(self):
        # Simple white circle on black
        image = Image.new('RGB', (64, 64), (0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.ellipse((10, 10, 54, 54), fill="white")
        # Add a play triangle for style
        dc.polygon([(26, 22), (26, 42), (44, 32)], fill="black")
        return image

    def minimize_to_tray(self):
        self.withdraw()
        print("Minimized to System Tray")

    def show_window(self, icon=None, item=None):
        self.after(0, self.deiconify)
        self.after(0, self.lift)

    def quit_app(self, icon=None, item=None):
        if hasattr(self, 'tray_icon'):
            self.tray_icon.stop()
        self.running = False
        self.destroy()
        sys.exit(0)
    


    def on_scroll(self, event):
        # 1. Check for Horizontal Scroll (2-finger side swipe)
        # On Windows, horizontal scroll is often reported as MouseWheel with Shift (0x1)
        if event.state & 0x1: 
            if event.delta > 0:
                self.run_task(self.svc_prev)
            else:
                self.run_task(self.svc_next)
            return

        # 2. Vertical Scroll (Volume)
        vk = 0xAF if event.delta > 0 else 0xAE
        try:
             windll.user32.keybd_event(vk, 0, 0, 0) # Press
             windll.user32.keybd_event(vk, 0, 2, 0) # Release
        except Exception as e:
             print(f"Volume Injection Error: {e}")


    def launch_settings(self):
        # Prefer python settings.py if it exists
        if os.path.exists("settings.py"):
            try:
                subprocess.Popen([sys.executable, "settings.py"], cwd=os.getcwd())
            except Exception as e:
                print(f"Failed to launch settings: {e}")
        else:
            try:
                 os.startfile("config.json")
            except: pass

    def on_drag(self, event):
        # 1. Gesture Detection (restricted to art area start)
        if self.gesture_start_time > 0 and not self.gesture_triggered:
            dx = event.x_root - self.gesture_start_x
            dt = time.time() - self.gesture_start_time
            
            if dt < 0.2: # Within 200ms
                if abs(dx) > 100: # Over 100 pixels
                    if dx > 100:
                        self.run_task(self.svc_next)
                    else:
                        self.run_task(self.svc_prev)
                    self.gesture_triggered = True
                    # If gesture triggered, cancel any potential window drag
                    self.dragging_window = False
                    return

        if self.dragging_slider:
            self.update_seek_visual(event.x)
        elif self.dragging_window:
            dx = event.x_root - self.drag_start_x
            dy = event.y_root - self.drag_start_y
            self.current_x = self.win_start_x + dx
            self.current_y = self.win_start_y + dy
            # Force target to follow current exactly during drag
            self.target_x = self.current_x
            self.target_y = self.current_y
            self.geometry(f"+{int(self.current_x)}+{int(self.current_y)}")
        elif self.resizing_window:
            dx = event.x_root - self.drag_start_x
            dy = event.y_root - self.drag_start_y
            self.width = max(300, self.win_start_w + dx)
            self.height = max(100, self.win_start_h + dy)
            # We don't call setup_ui here anymore to avoid jitter/resetting items.
            # The physics loop (animate_physics) will handle the visual scaling.
            
    def on_release(self, event):
        # Reset Geature State
        self.gesture_start_time = 0
        self.gesture_triggered = False

        if self.dragging_slider:
            self.dragging_slider = False
            bx1, _, bx2, _ = self.bar_coords
            clamped_x = max(bx1, min(event.x, bx2))
            pct = (clamped_x - bx1) / (bx2 - bx1)
            
            if hasattr(self, 'current_media_end') and self.current_media_end > 0:
                seek_sec = pct * self.current_media_end
                self.run_task(lambda: self.svc_seek(seek_sec))
        
        if self.dragging_window or self.resizing_window:
            if self.resizing_window:
                self.setup_ui() # Finalize the new layout once resizing stops
            
            # Save position for Normal mode
            if self.mode == "normal":
                self.normal_geometry = f"{int(self.width)}x{int(self.height)}+{int(self.current_x)}+{int(self.current_y)}"
            
            self.dragging_window = False
            self.resizing_window = False
            self.update_dock_side()
            self.save_config()

    def update_seek_visual(self, x):
        bx1, _, bx2, _ = self.bar_coords
        clamped_x = max(bx1, min(x, bx2))
        self.canvas.coords(self.bar_val_id, bx1, self.bar_y, clamped_x, self.bar_y)
        self.canvas.coords(self.dot_id, clamped_x-5, self.bar_y-5, clamped_x+5, self.bar_y+5)
        
        if hasattr(self, 'current_media_end') and self.current_media_end > 0:
            pct = (clamped_x - bx1) / (bx2 - bx1)
            sec = pct * self.current_media_end
            t_str = self.format_time(sec)
            self.canvas.itemconfig(self.lbl_curr_time, text=t_str)
            if hasattr(self, 'lbl_curr_time_shadow'):
                self.canvas.itemconfig(self.lbl_curr_time_shadow, text=t_str)

    def pulse_btn(self, item):
        # Determine original color if possible, or just use white/artist_fg
        tags = self.canvas.gettags(item)
        orig_color = self.fg_color
        if "btn_shuffle" in tags or "btn_loop" in tags:
             orig_color = self.artist_fg
             
        self.canvas.itemconfig(item, fill=self.sub_color)
        self.after(100, lambda: self.canvas.itemconfig(item, fill=orig_color))

    def format_time(self, seconds):
        if seconds < 0: seconds = 0
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}:{s:02d}"

    def on_mouse_move(self, event):
        # Handle seek bar hover cursor
        if self.show_progress:
            x, y = event.x, event.y
            sx1, sy1, sx2, sy2 = self.seek_hitbox
            if sx1 <= x <= sx2 and sy1 <= y <= sy2:
                self.canvas.config(cursor="hand2")
                return
        
        # If not over seek bar or buttons (handled by tag_bind)
        # We check overlapping for buttons just in case or let tag_bind handle it.
        # Actually tag_bind handles it better. But we need to reset if not over anything.
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        is_over_button = any(tag in self.canvas.gettags(i) for i in items for tag in ["btn_prev", "btn_play", "btn_next"])
        
        if not is_over_button:
            self.canvas.config(cursor="")

    # --- Animation ---
    def animate_physics(self):
        if self.dragging_window or self.resizing_window:
            self.vel_x = self.vel_y = self.vel_w = self.vel_h = 0
            self.after(16, self.animate_physics)
            return

        # Target selection
        target_w = self.width
        target_h = self.height
        target_x = self.target_x
        target_y = self.target_y
        
        # Center x for island
        if self.mode == "island":
            screen_w = self.winfo_screenwidth()
            target_x = (screen_w - target_w) // 2

        # Apple Studio Bouncy Spring Physics (Optimized for speed)
        # Use values from config if available, otherwise defaults
        speed_fac = (getattr(self, 'animation_speed', 0.2) / 0.2)
        stiffness = getattr(self, 'stiffness', 550.0) * speed_fac
        damping = getattr(self, 'damping', 38.0) * math.sqrt(speed_fac)
        dt = 0.016
        
        def spring_step(curr, target, vel):
            force = stiffness * (target - curr) - damping * vel
            vel += force * dt
            curr += vel * dt
            return curr, vel

        self.current_width, self.vel_w = spring_step(self.current_width, target_w, self.vel_w)
        self.current_height, self.vel_h = spring_step(self.current_height, target_h, self.vel_h)
        self.current_x, self.vel_x = spring_step(self.current_x, target_x, self.vel_x)
        self.current_y, self.vel_y = spring_step(self.current_y, target_y, self.vel_y)

        # Snap to target when close enough to stop microscopic oscillation
        eps = 0.05
        v_eps = 0.1
        if abs(target_w - self.current_width) < eps and abs(self.vel_w) < v_eps: self.current_width = target_w; self.vel_w = 0
        if abs(target_h - self.current_height) < eps and abs(self.vel_h) < v_eps: self.current_height = target_h; self.vel_h = 0
        if abs(target_x - self.current_x) < eps and abs(self.vel_x) < v_eps: self.current_x = target_x; self.vel_x = 0
        if abs(target_y - self.current_y) < eps and abs(self.vel_y) < v_eps: self.current_y = target_y; self.vel_y = 0

        self.geometry(f"{int(self.current_width)}x{int(self.current_height)}+{int(self.current_x)}+{int(self.current_y)}")
        
        # Update Canvas Elements
        self.update_ui_animation()

        self.after(16, self.animate_physics) 

    def update_ui_animation(self):
        # Update Background Rounded Rect (No flickering)
        # Force strict compliance with mode dimensions for the background shape
        draw_w, draw_h = self.current_width, self.current_height
        
        # In island mode, if we are 'settled', snap to exact island dims to avoid
        # any floating-point jitter or residue from normal mode transitions
        if self.mode == "island" and abs(self.current_width - self.island_width) < 1:
             draw_w, draw_h = self.island_width, self.island_height
        
        # URGENT: Ensure canvas matches current window size to avoid clipping
        self.canvas.config(width=int(draw_w), height=int(draw_h))
             
        points = get_rounded_rect_points(0, 0, draw_w, draw_h, radius=self.border_radius)
        self.canvas.coords(self.bg_id, *points)
        
        has_glow = self.canvas.itemcget(self.bg_img_id, "image") != ""
        if has_glow:
            self.canvas.coords(self.bg_img_id, self.current_width/2, self.current_height/2)
            self.canvas.itemconfig(self.bg_id, state="hidden")
        else:
            self.canvas.itemconfig(self.bg_id, state="normal")

        # Reposition and scaling of art
        scale = self.current_height / 125.0
        padding = max(10, self.current_height * 0.12)
        target_h = int(self.current_height - (padding * 2.2))
        
        # Calculate aspect ratio
        art_w, art_h = target_h, target_h # Default square
        if hasattr(self, 'last_pil_img') and self.last_pil_img:
            ow, oh = self.last_pil_img.size
            aspect = ow / oh
            art_w = target_h * aspect
            art_h = target_h
            # Cap width to 45% of widget
            if art_w > self.current_width * 0.45:
                art_w = self.current_width * 0.45
                art_h = art_w / aspect
        
        art_x = padding + art_w // 2
        art_y = self.current_height / 2
        self.last_art_w = art_w # Store for update_media_state
        
        self.canvas.coords(self.art_id, art_x, art_y)
        
        if hasattr(self, 'last_pil_img') and self.last_pil_img:
            # We use art_w as the key for redraw check
            if not hasattr(self, 'last_drawn_w') or abs(self.last_drawn_w - art_w) > 3:
                self.last_drawn_w = art_w
                self.redraw_art_image(art_w, art_h)
            self.canvas.itemconfig(self.art_id, state="normal")
            if hasattr(self, 'placeholder_id_rect'):
                self.canvas.itemconfig(self.placeholder_id_rect, state="hidden")
        else:
            self.canvas.itemconfig(self.art_id, state="hidden")
            # Handle placeholder (stays square)
            art_size = target_h
            x1, y1 = padding, art_y - art_size/2
            x2, y2 = x1 + art_size, y1 + art_size
            if not hasattr(self, 'placeholder_id_rect'):
                self.placeholder_id_rect = create_rounded_rect(self.canvas, x1, y1, x2, y2, radius=int(art_size*0.25), fill="#111111", tags="art_group")
            else:
                self.canvas.itemconfig(self.placeholder_id_rect, state="normal")
                p_points = get_rounded_rect_points(x1, y1, x2, y2, radius=int(art_size*0.25))
                self.canvas.coords(self.placeholder_id_rect, *p_points)
            art_w = art_size # for layout calc

        # Reposition UI Elements
        right_margin = 35 * scale
        art_end_x = padding + art_w + right_margin
        text_x = art_end_x + (self.current_width - art_end_x - (25 * scale)) // 2
        
        # Vertical stack center values
        if self.show_progress and self.show_controls:
            title_y, artist_y, ctrl_y, bar_y = self.current_height*0.22, self.current_height*0.40, self.current_height*0.64, self.current_height*0.86
        elif self.show_progress:
            title_y, artist_y, bar_y, ctrl_y = self.current_height*0.35, self.current_height*0.52, self.current_height*0.85, -100
        elif self.show_controls:
            title_y, artist_y, ctrl_y, bar_y = self.current_height*0.32, self.current_height*0.50, self.current_height*0.75, -100
        else:
            title_y, artist_y, ctrl_y, bar_y = self.current_height*0.42, self.current_height*0.60, -100, -100

        # Apply transition offsets (for smooth song change)
        dy_t = getattr(self, 'title_dy', 0)
        dy_a = getattr(self, 'artist_dy', 0)
        
        offset = 0.8 * scale
        self.canvas.coords(self.title_shadow_id, text_x + offset, title_y + dy_t + offset)
        self.canvas.coords(self.title_id, text_x, title_y + dy_t)
        
        self.canvas.coords(self.artist_shadow_id, text_x + offset, artist_y + dy_a + offset)
        self.canvas.coords(self.artist_id, text_x, artist_y + dy_a)
        
        if self.show_progress:
            bar_w = (self.current_width - art_end_x - right_margin) * 0.75
            bar_x1, bar_x2 = text_x - bar_w//2, text_x + bar_w//2
            self.bar_coords = (bar_x1, bar_y, bar_x2, bar_y)
            
            self.canvas.coords(self.bar_bg_id, bar_x1, bar_y, bar_x2, bar_y)
            self.canvas.coords(self.lbl_curr_time_shadow, bar_x1 - (10 * scale) + 0.5, bar_y + 0.5)
            self.canvas.coords(self.lbl_curr_time, bar_x1 - (10 * scale), bar_y)
            self.canvas.coords(self.lbl_total_time_shadow, bar_x2 + (10 * scale) + 0.5, bar_y + 0.5)
            self.canvas.coords(self.lbl_total_time, bar_x2 + (10 * scale), bar_y)
            
            if not self.dragging_slider:
                new_x = bar_x1 + (bar_w * self.last_ratio)
                self.canvas.coords(self.bar_val_id, bar_x1, bar_y, new_x, bar_y)
                dot_r = 5.0 * scale
                self.canvas.coords(self.dot_id, new_x-dot_r, bar_y-dot_r, new_x+dot_r, bar_y+dot_r)
        
        if self.show_controls:
            btn_offset = 48 * scale
            s = 9 * scale
            gap = 0.5 * scale
            
            # Reposition Play Button
            self.canvas.coords(self.btn_play_id, text_x, ctrl_y)
            self.update_play_pause_ui(self.last_status, text_x, ctrl_y)
            
            # Reposition Prev/Next Buttons (Must work in ALL modes)
            prev_items = self.canvas.find_withtag("btn_prev")
            if len(prev_items) >= 2:
                self.canvas.coords(prev_items[0], text_x - btn_offset, ctrl_y - s, text_x - btn_offset, ctrl_y + s, text_x - btn_offset - s, ctrl_y)
                self.canvas.coords(prev_items[1], text_x - btn_offset + s + gap, ctrl_y - s, text_x - btn_offset + s + gap, ctrl_y + s, text_x - btn_offset + gap, ctrl_y)

            next_items = self.canvas.find_withtag("btn_next")
            if len(next_items) >= 2:
                self.canvas.coords(next_items[0], text_x + btn_offset, ctrl_y - s, text_x + btn_offset, ctrl_y + s, text_x + btn_offset + s, ctrl_y)
                self.canvas.coords(next_items[1], text_x + btn_offset - s - gap, ctrl_y - s, text_x + btn_offset - s - gap, ctrl_y + s, text_x + btn_offset - gap, ctrl_y)

        if self.mode == "normal":
            # Reposition Resize Handle
            self.canvas.coords("resize_handle", self.current_width-30, self.current_height-30, self.current_width, self.current_height)

        # Ensure Z-Order
        self.canvas.tag_lower(self.bg_img_id)
        self.canvas.tag_lower(self.bg_id)
        self.canvas.tag_raise("art_group")
        self.canvas.tag_raise("expanded_ui")

    def redraw_art_image(self, w, h):
        if not hasattr(self, 'last_pil_img'): return
        try:
             radius = int(min(w, h) * 0.25)
             processed_img = make_rounded_image(self.last_pil_img, w, h, radius=radius)
             self.tk_img_current = ImageTk.PhotoImage(processed_img)
             self.canvas.itemconfig(self.art_id, image=self.tk_img_current)
        except: pass


    def check_mouse(self):
        # 0. Check for Context Menu or Settings Open - FORCE VISIBLE
        ctx_open = getattr(self, 'ctx_menu_open', False)
        
        settings_open = False
        if hasattr(self, 'settings_process') and self.settings_process:
            if self.settings_process.poll() is None: # Still running
                settings_open = True
            else:
                self.settings_process = None # Clean up
        
        if ctx_open or settings_open:
            if self.mode == "island":
                 self.target_y = self.y_visible
            self.after(200, self.check_mouse) # Slower poll needed
            return

        if self.dragging_window or self.resizing_window:
            self.after(30, self.check_mouse)
            return

        mx, my = get_mouse_pos()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        
        should_show = False
        
        # 1. Check if mouse is in the "Lip" zone for current dock side
        if self.dock_side == "top":
            trigger_w = self.width + 30
            zone_x1 = self.current_x - 15
            zone_x2 = self.current_x + self.width + 15
            if zone_x1 <= mx <= zone_x2 and my <= self.hover_zone_height:
                should_show = True
        elif self.dock_side == "left":
            if mx <= self.hover_zone_height and self.current_y <= my <= self.current_y + self.height:
                should_show = True
        elif self.dock_side == "right":
            if mx >= screen_w - self.hover_zone_height and self.current_y <= my <= self.current_y + self.height:
                should_show = True

        # 2. Check if mouse is within the visible widget + tight buffer
        if not should_show:
            wx, wy = self.winfo_x(), self.winfo_y()
            # Reduced buffer to 10px for ultra-precision
            buffer = 10
            if wx - buffer <= mx <= wx + self.width + buffer and wy - buffer <= my <= wy + self.height + buffer:
                # Only keep visible if it's already somewhat visible
                if self.dock_side == "top" and self.current_y > self.y_hidden + 2: should_show = True
                elif self.dock_side == "left" and self.current_x > self.x_hidden + 2: should_show = True
                elif self.dock_side == "right" and self.current_x < self.x_hidden - 2: should_show = True
                elif self.dock_side is None: should_show = True

        if self.sticky:
            should_show = True

        # Handle Hide Delay
        if should_show:
            self.mouse_leave_time = 0
        else:
            if self.mouse_leave_time == 0:
                self.mouse_leave_time = time.time()
            
            elapsed = (time.time() - self.mouse_leave_time) * 1000
            if elapsed < self.auto_hide_delay:
                should_show = True

        if self.dock_side == "top":
            self.target_y = self.y_visible if should_show else self.y_hidden
            self.target_x = self.current_x
        elif self.dock_side == "left":
            self.target_x = self.x_visible if should_show else self.x_hidden
            self.target_y = self.current_y
        elif self.dock_side == "right":
            self.target_x = self.x_visible if should_show else self.x_hidden
            self.target_y = self.current_y
        else:
            self.target_x = self.current_x
            self.target_y = self.current_y

        self.after(30, self.check_mouse)

    def check_config_reload(self):
        if os.path.exists("config.json"):
            m = os.path.getmtime("config.json")
            if m > self.last_config_mtime:
                self.load_config()
                self.setup_dimensions()
                self.last_config_mtime = m
        self.after(200, self.check_config_reload)

    def launch_settings(self):
        # Prefer python settings.py if it exists
        if os.path.exists("settings.py"):
            try:
                # Store process to track if it is open
                self.settings_process = subprocess.Popen([sys.executable, "settings.py"], cwd=os.getcwd())
            except Exception as e:
                print(f"Failed to launch settings: {e}")
        else:
            try:
                 os.startfile("config.json")
            except: pass
    def run_async_loop(self):
        try:
            # Initialize COM for the background thread
            try:
                import ctypes
                ctypes.windll.ole32.CoInitializeEx(0, 0x0) # COINIT_MULTITHREADED
            except: pass

            print("DEBUG: Background thread started.")
            asyncio.set_event_loop(self.loop)
            print("DEBUG: Event loop set. Starting run_forever().")
            sys.stdout.flush()
            self.loop.create_task(self.monitor_media())
            self.loop.run_forever()
        except Exception as e:
            print(f"DEBUG: Background loop CRASHED: {e}")
            sys.stdout.flush()

    def run_task(self, coro_func):
        if self.loop:
            is_active = self.loop.is_running()
            name = getattr(coro_func, '__name__', 'lambda')
            print(f"DEBUG: run_task launching {name} (Loop Running: {is_active})...")
            sys.stdout.flush()
            try:
                # If it's a bound method or function, call it to get the coro
                res = coro_func()
                if asyncio.iscoroutine(res):
                    asyncio.run_coroutine_threadsafe(res, self.loop)
                    print(f"DEBUG: {name} scheduled successfully.")
                else:
                    print(f"DEBUG: {name} was not a coroutine (sync?).")
            except Exception as e:
                print(f"DEBUG: FAILED to schedule {name}: {e}")
            sys.stdout.flush()

    async def monitor_media(self):
        if not WINRT_AVAILABLE: return
        print("DEBUG: monitor_media task starting...")
        sys.stdout.flush()
        try:
            self.manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
            print("DEBUG: manager.request_async() success.")
        except Exception as e:
            print(f"DEBUG: manager.request_async() FAILED: {e}")
            sys.stdout.flush()
            return
        
        print(f"DEBUG: monitor_media Entering loop (Running: {self.running})")
        sys.stdout.flush()
        
        while self.running:
            # SMART SESSION SELECTION: Prioritize playing sessions over paused ones
            try:
                all_sessions = self.manager.get_sessions()
                
                # TWO-PASS FILTERING: First find if ANY session is playing
                has_playing_session = False
                for session in all_sessions:
                    try:
                        info = session.get_playback_info()
                        if info and info.playback_status == 4:  # Playing
                            has_playing_session = True
                            break
                    except:
                        continue
                
                best_session = None
                best_priority = -1  # Higher = better
                
                for session in all_sessions:
                    try:
                        info = session.get_playback_info()
                        if not info:
                            continue
                        
                        status = info.playback_status
                        app_id = session.source_app_user_model_id
                        
                        # AGGRESSIVE FILTER: If ANY session is playing, IGNORE all non-playing sessions
                        if has_playing_session and status != 4:
                            continue  # Skip paused/stopped sessions entirely
                        
                        # Calculate priority
                        priority = 0
                        
                        # Playing sessions get +100 priority
                        if status == 4:  # Playing
                            priority += 100
                        
                        # Spotify gets +50 priority
                        if "Spotify" in app_id:
                            priority += 50
                        
                        # Edge/Chrome (for Spotify Web) gets +30 if playing
                        if status == 4 and any(browser in app_id for browser in ["edge", "chrome", "firefox"]):
                            props = await session.try_get_media_properties_async()
                            if props and props.title and ("Spotify" in props.title or "Spotify" in (props.artist or "")):
                                priority += 30
                        
                        # Update best session
                        if priority > best_priority:
                            best_priority = priority
                            best_session = session
                    
                    except Exception as e:
                        continue
                
                # Use the best session found, but apply hold time logic
                current_time = time.time()
                should_hold = False
                
                if self.last_session_id and (current_time - self.last_session_lock_time) < self.session_hold_duration:
                    # We're in hold period - only switch if new session is MUCH better
                    if best_priority < self.last_session_priority + 50:
                        # New session isn't significantly better, keep current
                        should_hold = True
                        # Try to find the current session in the list
                        for session in all_sessions:
                            try:
                                if session.source_app_user_model_id == self.last_session_id:
                                    best_session = session
                                    best_priority = self.last_session_priority
                                    break
                            except:
                                continue
                
                if not should_hold and best_session:
                    # Update lock
                    try:
                        self.last_session_id = best_session.source_app_user_model_id
                        self.last_session_priority = best_priority
                        self.last_session_lock_time = current_time
                    except:
                        pass
                
                self.session = best_session
                
            except Exception as e:
                # Fallback to get_current_session if scanning fails
                self.session = self.manager.get_current_session()
            
            if self.session:
                try:
                    thumb_stream = None
                    props = await self.session.try_get_media_properties_async()
                    
                    # HOLD LOGIC: If properties are empty OR generic during track transition, don't update yet
                    # Some sessions report empty properties for a few ms when track changes
                    title = (props.title or "").strip()
                    artist = (props.artist or "").strip()
                    
                    # More aggressive generic check to catch browser/app placeholders like "Spotify" or "-"
                    is_generic = (not title or title.lower() in ["unknown title", "spotify", "no media", "play something..."]) and \
                                 (not artist or artist.lower() in ["unknown artist", "artist", "-", "."])
                    
                    if is_generic and (time.time() - self.last_media_time) < self.content_hold_duration:
                        # Skip this tick to hold previous content if we lost info or got generic info briefly
                        await asyncio.sleep(0.3)
                        continue

                    # SECONDARY FILTER: Even if artist is valid, if Title is bad, don't show it during hold
                    bad_title = not title or title.lower() in ["unknown title", "spotify", "no media", "play something..."]
                    if bad_title and (time.time() - self.last_media_time) < self.content_hold_duration:
                        await asyncio.sleep(0.3) 
                        continue

                    if not title: title = "Unknown Title"
                    if not artist: artist = "Unknown Artist"
                    
                    # FINAL SAFETY: If we resolved to Unknown Title, block it for 5s
                    if title == "Unknown Title" and (time.time() - self.last_media_time) < self.content_hold_duration:
                        await asyncio.sleep(0.3)
                        continue
                    thumb_data = None
                    if props.thumbnail:
                        try:
                            thumb_stream = await props.thumbnail.open_read_async()
                            from winrt.windows.storage import streams as winrt_streams
                            from winrt.windows.security.cryptography import CryptographicBuffer as crypto
                            reader = winrt_streams.DataReader(thumb_stream)
                            await reader.load_async(thumb_stream.size)
                            ibuffer = reader.read_buffer(thumb_stream.size)
                            arr = crypto.copy_to_byte_array(ibuffer)
                            thumb_data = bytes(arr)
                        except Exception as thumb_err:
                            print(f"WARNING: Thumbnail fetch failed for '{title}': {thumb_err}")
                            thumb_data = None
                    
                    timeline = self.session.get_timeline_properties()
                    pos = timeline.position.total_seconds() if timeline.position else 0
                    end = timeline.end_time.total_seconds() if timeline.end_time else 1
                    
                    info = self.session.get_playback_info()
                    status = info.playback_status
                    
                    if status == 4:
                         last_updated = timeline.last_updated_time
                         if last_updated:
                             now = datetime.datetime.now(datetime.timezone.utc)
                             diff = (now - last_updated).total_seconds()
                             if diff > 0: pos += diff
                    
                    if pos > end: pos = end
                    
                    shuffle = info.is_shuffle_active if info else False
                    repeat = info.auto_repeat_mode if info else 0 # 0=None, 1=Track, 2=List
                    
                    self.after(0, self.update_media_state, title, artist, pos, end, status, thumb_data, shuffle, repeat)
                    
                    # Update last media time since we successfully got media
                    self.last_media_time = time.time()
                except Exception as e:
                    print(f"DEBUG: monitor_media internal error: {e}")
                    sys.stdout.flush()
            else:
                 # No session available - use CONTENT HOLD to prevent flash
                 current_time = time.time()
                 time_since_media = current_time - self.last_media_time
                 
                 # Only show "No Media" if we've had no session for a LONG time
                 if time_since_media > self.content_hold_duration:
                     try:
                        all_sessions = self.manager.get_sessions()
                        if not all_sessions or len(all_sessions) == 0:
                            # Only then show No Media
                            self.after(0, self.update_media_state, "No Media", "Play something...", 0, 100, 5, None, False, 0)
                        else:
                            # We have sessions but none selected? Try to grab the first active one
                            for s in all_sessions:
                                info = s.get_playback_info()
                                if info and info.playback_status == 4: # Playing
                                    self.session = s
                                    break
                     except:
                        pass
                 # else: Keep showing the last known content (do nothing)
            
            await asyncio.sleep(0.5)  # Slightly slower but safer polling

    async def svc_play_pause(self):
        if self.session: await self.session.try_toggle_play_pause_async()
    async def svc_next(self):
        if self.session: await self.session.try_skip_next_async()
    async def svc_prev(self):
        if self.session: await self.session.try_skip_previous_async()
        
    async def svc_seek(self, seconds):
        if self.session:
            print(f"Attempting Seek to {seconds}...")
            try:
                ticks = int(seconds * 10_000_000)
                await self.session.try_change_playback_position_async(ticks)
            except Exception as e:
                print(f"Seek failed: {e}")

    async def svc_toggle_shuffle(self):
        print("\n[SVC] SHUFFLE TASK STARTING...")
        sys.stdout.flush()
        if not hasattr(self, 'manager') or self.manager is None:
            print("[SVC] ERROR: Global manager is None. Background init failed?")
            sys.stdout.flush()
            return
        
        print("[SVC] Calling get_sessions()...")
        sys.stdout.flush()
        try:
            sessions = self.manager.get_sessions()
            print(f"[SVC] get_sessions() returned {len(sessions)} items.")
        except Exception as e:
            print(f"[SVC] CRITICAL ERROR calling get_sessions(): {e}")
            sessions = []
        sys.stdout.flush()
        
        print("\n[SVC] --- Diagnostic Session Scan (Shuffle) ---")
        sys.stdout.flush()
        target_session = None
        is_browser = False
        
        for s in sessions:
            try:
                source = s.source_app_user_model_id
                print(f"[SVC] Scanning Session: {source}")
                
                # Check for capabilities first if we think it might be a match
                match = False
                if "Spotify" in source:
                    match = True
                    print(f"[SVC] Potential Match (App ID): {source}")
                else:
                    is_browser_check = any(b in source.lower() for b in ["edge", "chrome", "firefox", "browser"])
                    if is_browser_check:
                        props = await s.try_get_media_properties_async()
                        if props and ("Spotify" in (props.title or "") or "Spotify" in (props.artist or "")):
                            match = True
                            print(f"[SVC] Potential Match (Browser): {props.title}")

                if match:
                    # Verify capabilities
                    info = s.get_playback_info()
                    caps = info.controls if info else None
                    
                    # For Shuffle Toggle
                    can_do = caps.is_shuffle_enabled if (caps and hasattr(caps, "is_shuffle_enabled")) else False
                    
                    if can_do:
                        target_session = s
                        is_browser = any(b in source.lower() for b in ["edge", "chrome", "firefox", "browser"])
                        print(f"[SVC] >>> Match found with SHUFFLE support!")
                        break
                    else:
                        print(f"[SVC] Match found but Shuffle is NOT enabled/supported by this source.")
                
                sys.stdout.flush()
            except Exception as e:
                print(f"[SVC] Scan error: {e}")
                pass
        
        # Fallback to current if no specific match
        if not target_session:
            print("[SVC] No specific Spotify session found. Using System 'Current' session.")
            target_session = self.manager.get_current_session()
            if target_session:
                source_id = target_session.source_app_user_model_id
                is_browser = any(b in source_id.lower() for b in ["edge", "chrome", "firefox", "browser"])

        if target_session:
            try:
                info = target_session.get_playback_info()
                source_id = target_session.source_app_user_model_id
                
                # Log Capabilities
                caps = info.controls if info else None
                can_shuffle = caps.is_shuffle_enabled if caps else "Unknown"
                
                print(f"[SVC] Targeted Session: {source_id}")
                print(f"[SVC] Capabilities: Shuffle Supported = {can_shuffle}")
                
                current = info.is_shuffle_active if (info and info.is_shuffle_active is not None) else False
                target_state = not current
                print(f"[SVC] Executing Shuffle: {current} -> {target_state}")
                
                success = await target_session.try_change_shuffle_active_async(target_state)
                print(f"[SVC] Result: {success}")
                if not success and is_browser:
                    print("[SVC] NOTE: Browsers often block Shuffle/Repeat commands via Windows API.")
            except Exception as e:
                print(f"[SVC] CRITICAL ERROR: {e}")
        else:
            print("[SVC] No active media sessions found at all.")

    async def svc_toggle_repeat(self):
        print("\n[SVC] REPEAT TASK STARTING...")
        sys.stdout.flush()
        if not hasattr(self, 'manager') or self.manager is None:
            print("[SVC] ERROR: Global manager is None. Background init failed?")
            sys.stdout.flush()
            return
            
        print("[SVC] Calling get_sessions()...")
        sys.stdout.flush()
        try:
            sessions = self.manager.get_sessions()
            print(f"[SVC] get_sessions() returned {len(sessions)} items.")
        except Exception as e:
            print(f"[SVC] CRITICAL ERROR calling get_sessions(): {e}")
            sessions = []
        sys.stdout.flush()
        
        print("\n[SVC] --- Diagnostic Session Scan (Repeat) ---")
        sys.stdout.flush()
        target_session = None
        
        is_browser = False
        for s in sessions:
            try:
                source = s.source_app_user_model_id
                print(f"[SVC] Scanning Session: {source}")
                
                match = False
                if "Spotify" in source:
                    match = True
                    print(f"[SVC] Potential Match (App ID): {source}")
                else:
                    is_browser_check = any(b in source.lower() for b in ["edge", "chrome", "firefox", "browser"])
                    if is_browser_check:
                        props = await s.try_get_media_properties_async()
                        if props and ("Spotify" in (props.title or "") or "Spotify" in (props.artist or "")):
                            match = True
                            print(f"[SVC] Potential Match (Browser): {props.title}")

                if match:
                    info = s.get_playback_info()
                    caps = info.controls if info else None
                    can_do = caps.is_repeat_enabled if (caps and hasattr(caps, "is_repeat_enabled")) else False
                    
                    if can_do:
                        target_session = s
                        is_browser = any(b in source.lower() for b in ["edge", "chrome", "firefox", "browser"])
                        print(f"[SVC] >>> Match found with REPEAT support!")
                        break
                    else:
                        print(f"[SVC] Match found but Repeat is NOT enabled/supported by this source.")
                sys.stdout.flush()
            except Exception as e:
                pass
        
        if not target_session:
            print("[SVC] No specific Spotify session found. Using System 'Current' session.")
            target_session = self.manager.get_current_session()
            if target_session:
                source = target_session.source_app_user_model_id
                is_browser = any(b in source.lower() for b in ["edge", "chrome", "firefox", "browser"])

        if target_session:
            try:
                info = target_session.get_playback_info()
                source_id = target_session.source_app_user_model_id
                
                caps = info.controls if info else None
                can_repeat = caps.is_repeat_enabled if caps else "Unknown"
                
                print(f"[SVC] Targeted Session: {source_id}")
                print(f"[SVC] Capabilities: Repeat Supported = {can_repeat}")
                
                # Safe Enum-to-Int cast
                current = int(info.auto_repeat_mode) if (info and info.auto_repeat_mode is not None) else 0
                next_mode = 2 if current == 0 else 0 # Toggle List/None
                
                print(f"[SVC] Executing Repeat: {current} -> {next_mode}")
                
                success = await target_session.try_change_auto_repeat_mode_async(next_mode)
                print(f"[SVC] Result: {success}")
                if not success and is_browser:
                    print("[SVC] NOTE: Browsers often block Shuffle/Repeat commands via Windows API.")
            except Exception as e:
                print(f"[SVC] CRITICAL ERROR: {e}")
        else:
             print("[SVC] No active media sessions found at all.")
    
    # --- Tooltips ---
    def schedule_tooltip(self, text, event):
        self.cancel_tooltip()
        self.tooltip_text = text
        self.tooltip_job = self.after(600, lambda: self.show_tooltip(event.x_root, event.y_root))
        
    def cancel_tooltip(self, event=None):
        if self.tooltip_job:
            self.after_cancel(self.tooltip_job)
            self.tooltip_job = None
        self.hide_tooltip()
        
    def show_tooltip(self, x, y):
        if not self.tooltip_text: return
        self.hide_tooltip()
        
        try:
            tw = tk.Toplevel(self)
            tw.wm_overrideredirect(True)
            tw.wm_attributes("-topmost", True)
            
            # Position above cursor
            tw.geometry(f"+{x+10}+{y-25}")
            
            label = tk.Label(tw, text=self.tooltip_text, justify='left',
                           background="#222222", fg="#FFFFFF",
                           relief='solid', borderwidth=1,
                           font=("Segoe UI Variable Text", 9))
            label.pack(ipadx=5, ipady=2)
            self.tooltip_win = tw
        except Exception:
             pass
             
    def hide_tooltip(self):
        if self.tooltip_win:
            try:
                self.tooltip_win.destroy()
            except: pass
            self.tooltip_win = None

    async def focus_source_app(self):
        if self.session:
            app_id = self.session.source_app_user_model_id
            print(f"Trying to focus: {app_id}")
            if app_id:
                # Run in thread because EnumWindows is blocking-ish and uses heavy ctypes
                await self.loop.run_in_executor(None, lambda: FocusHelper().focus_app(app_id))

    def toggle_ambilight(self):
        """Toggle ambilight and restart widget for changes to apply"""
        self.ambilight_enabled = not self.ambilight_enabled
        self.save_config()
        # Restart to apply ambilight changes cleanly
        self.restart_app()

    # --- UI Update ---
    def update_media_state(self, title, artist, pos, end, status, thumb_stream, shuffle=False, repeat=0):
        try:
            self.current_media_end = end
            self.last_status = status
            
            # --- Enhanced Caching Check ---
            current_key = (title, artist)
            track_changed = (current_key != self.last_track_key)
            
            # Hash-based thumbnail tracking to detect actual image changes
            thumb_hash = None
            if thumb_stream:
                try:
                    import hashlib
                    thumb_hash = hashlib.md5(thumb_stream[:1024] if len(thumb_stream) > 1024 else thumb_stream).hexdigest()
                except:
                    thumb_hash = str(len(thumb_stream))  # Fallback to size
            
            thumb_changed = (thumb_hash != getattr(self, 'last_thumb_hash', None))
            
            # Additional check: If we have no art but we SHOULD have art, retry fetch
            needs_art_retry = (thumb_stream is not None and not hasattr(self, 'last_pil_img'))
            
            # Force refresh every 10 updates to catch edge cases
            if not hasattr(self, 'update_counter'):
                self.update_counter = 0
            self.update_counter += 1
            force_refresh = (self.update_counter % 10 == 0 and thumb_stream is not None)
            
            if track_changed or thumb_changed or needs_art_retry or force_refresh:
                self.last_track_key = current_key
                if thumb_hash:
                    self.last_thumb_hash = thumb_hash
                
                # --- SYNC TEXT AND ART ---
                # Only update art if we have data. 
                # If art is missing (None) but track changed, we might be in a gap.
                # But here we are just updating the visual state.
                
                if thumb_stream: 
                    try:
                        self.update_art_image(thumb_stream) 
                    except Exception as e:
                        print(f"ERROR: Failed to update album art: {e}")
                        if hasattr(self, 'placeholder_id_rect'):
                            self.canvas.itemconfig(self.placeholder_id_rect, state="normal")
                else:
                    # ONLY hide art if we've officially timed out on having any media
                    if (time.time() - self.last_media_time) > self.content_hold_duration or not title or title == "No Media":
                        if hasattr(self, 'last_pil_img'): 
                            del self.last_pil_img
                            if hasattr(self, 'last_thumb_hash'):
                                del self.last_thumb_hash
                        self.canvas.itemconfig(self.art_id, state="hidden")
                        self.apply_glow_bg(None)
            
            # --- Text Update Logic (SYNCED) ---
            # If track changed, we want to update text ONLY when art is ready or timeout
            if track_changed and not thumb_stream and (time.time() - self.last_media_time) < 2.0:
                 # If we have a new track but NO art yet, and it's been less than 2s, 
                 # HOLD OLD TEXT to match old art (which we are holding above)
                 return
            
            # Transition binary state colors (Optional: Can keep for other icons)
            # Binary state check
            is_sh_active = bool(shuffle)
            is_lp_active = (repeat is not None and int(repeat) > 0)
            scale = self.current_height / 125.0

            # Dynamic text truncation (respecting artwork width)
            # Use cached art_w or fallback to square assumption
            current_art_w = getattr(self, 'last_art_w', self.current_height * 0.8)
            padding = max(10, self.current_height * 0.12)
            right_margin = 35 * scale
            end_margin = 25 * scale
            available_w = self.current_width - (padding + current_art_w + right_margin + end_margin)
            max_text_width = available_w - 20 # Extra safety buffer
            
            def truncate_for_width(text, font, max_w):
                if font.measure(text) <= max_w: return text
                while font.measure(text + "...") > max_w and len(text) > 0:
                    text = text[:-1]
                return text + "..."

            final_title = truncate_for_width(title, self.font_title, max_text_width)
            final_artist = truncate_for_width(artist, self.font_artist, max_text_width)
            
            if final_artist.endswith("..."):
                 self.canvas.tag_bind(self.artist_id, "<Enter>", lambda e: self.schedule_tooltip(artist, e))
                 self.canvas.tag_bind(self.artist_id, "<Leave>", self.cancel_tooltip)
            else:
                 self.canvas.tag_bind(self.artist_id, "<Enter>", lambda e: self.canvas.config(cursor=""))
                 self.canvas.tag_bind(self.artist_id, "<Leave>", lambda e: None)

            # --- Fade Transitions ---
            self.fade_text(self.title_id, final_title)
            self.fade_text(self.artist_id, final_artist)

            self.canvas.itemconfig(self.lbl_total_time, text=self.format_time(end))
            if hasattr(self, 'lbl_total_time_shadow'):
                self.canvas.itemconfig(self.lbl_total_time_shadow, text=self.format_time(end))
            
            self.update_play_pause_ui(status)
            
            if not self.dragging_slider:
                self.canvas.itemconfig(self.lbl_curr_time, text=self.format_time(pos))
                if hasattr(self, 'lbl_curr_time_shadow'):
                    self.canvas.itemconfig(self.lbl_curr_time_shadow, text=self.format_time(pos))
                width = bx2 - bx1
                self.last_ratio = 0
                if pos is not None and end is not None and end > 0:
                    self.last_ratio = pos / end
                
                new_x = bx1 + (width * self.last_ratio)
                
                self.canvas.coords(self.bar_val_id, bx1, self.bar_y, new_x, self.bar_y)
                dot_r = 5.0 * (self.height / 125)
                self.canvas.coords(self.dot_id, new_x-dot_r, self.bar_y-dot_r, new_x+dot_r, self.bar_y+dot_r)

            # Logic moved to cache block above
            # if thumb_stream:
            #    self.run_task(lambda: self.fetch_thumbnail_bytes(thumb_stream))
            # elif not hasattr(self, 'last_pil_img'):
            #    self.canvas.itemconfig(self.art_id, state="hidden")
        except Exception as e:
            print(f"DEBUG: update_media_state error: {e}")
            import traceback
            traceback.print_exc()
            sys.stdout.flush()

    def update_play_pause_ui(self, status, text_x=None, ctrl_y=None):
        # status: 4 for playing (show pause icon), else show play icon
        scale = self.current_height / 125
        padding = max(10, self.current_height * 0.12)

        if text_x is None:
             # Use cached art_w or fallback to square assumption
             current_art_w = getattr(self, 'last_art_w', self.current_height - (padding * 2.2))
             right_margin = 35 * scale
             art_end_x = padding + current_art_w + right_margin
             text_x = art_end_x + (self.current_width - art_end_x - (25 * scale)) // 2
        
        if ctrl_y is None:
            if self.show_progress and self.show_controls:
                ctrl_y = self.current_height * 0.64
            elif self.show_controls:
                ctrl_y = self.current_height * 0.75
            else:
                ctrl_y = -100
            
        # We ensure play/pause items exist
        if not hasattr(self, 'pause_id_1'):
            self.pause_id_1 = self.canvas.create_line(0,0,0,0, tags=("btn_play", "play_icon", "expanded_ui"))
            self.pause_id_2 = self.canvas.create_line(0,0,0,0, tags=("btn_play", "play_icon", "expanded_ui"))
            self.play_id = self.canvas.create_polygon(0,0,0,0, tags=("btn_play", "play_icon", "expanded_ui"))

        if status == 4: # Playing -> Show Pause
            w = 5.5 * scale 
            h = 8.5 * scale 
            sep = 6.0 * scale 
            self.canvas.itemconfig(self.play_id, state="hidden")
            self.canvas.itemconfig(self.pause_id_1, state="normal", width=int(w), fill=self.fg_color, capstyle=tk.ROUND)
            self.canvas.itemconfig(self.pause_id_2, state="normal", width=int(w), fill=self.fg_color, capstyle=tk.ROUND)
            self.canvas.coords(self.pause_id_1, text_x - sep, ctrl_y - h, text_x - sep, ctrl_y + h)
            self.canvas.coords(self.pause_id_2, text_x + sep, ctrl_y - h, text_x + sep, ctrl_y + h)
        else: # Paused -> Show Play
            s = 9.5 * scale
            line_w = int(2.5 * scale)
            self.canvas.itemconfig(self.pause_id_1, state="hidden")
            self.canvas.itemconfig(self.pause_id_2, state="hidden")
            self.canvas.itemconfig(self.play_id, state="normal", fill=self.fg_color, outline=self.fg_color, width=line_w)
            self.canvas.coords(self.play_id, text_x - s/1.5, ctrl_y - s, text_x - s/1.5, ctrl_y + s, text_x + s, ctrl_y)
    async def fetch_thumbnail_bytes(self, stream):
        try:
            from winrt.windows.storage import streams
            from winrt.windows.security.cryptography import CryptographicBuffer as crypto
            
            reader = streams.DataReader(stream)
            await reader.load_async(stream.size)
            ibuffer = reader.read_buffer(stream.size)
            arr = crypto.copy_to_byte_array(ibuffer)
            data = bytes(arr) 
            self.after(0, self.update_art_image, data)
        except Exception:
            pass



    def apply_glow_bg(self, glow_img):
        if not self.running: return
        if glow_img:
            self.tk_glow_bg = ImageTk.PhotoImage(glow_img)
            self.canvas.itemconfig(self.bg_img_id, image=self.tk_glow_bg)
            # Ensure background stays at bottom
            self.canvas.tag_lower(self.bg_img_id)
            self.canvas.tag_lower(self.bg_id)
            
            # Hide solid rect to show glow
            self.canvas.itemconfig(self.bg_id, state="hidden")
        else:
            self.canvas.itemconfig(self.bg_img_id, image="")
            self.canvas.itemconfig(self.bg_id, state="normal", fill=self.island_color)

    def update_art_image(self, data):
        try:
            self.is_fetching_art = False
            self.last_pil_img = Image.open(io.BytesIO(data))
            self.last_drawn_size = -1 
            self.last_drawn_w = -1
            self.update_ui_animation() 
            if hasattr(self, 'placeholder_id_rect'):
                 self.canvas.itemconfig(self.placeholder_id_rect, state="hidden")
            
            # --- Ambilight Trigger ---
            # Enforce mode-specific dimensions for the glow generation
            # to prevent "ghosting" of the previous mode's size during transitions
            if self.mode == "island":
                w, h = self.island_width, self.island_height
                r = self.island_border_radius
            else:
                w, h = self.width, self.height # In normal mode, width/height are authoritative
                r = self.normal_border_radius
                
            self.loop.run_in_executor(None, lambda: self.async_process_background(self.last_pil_img, w, h, r))
                 
        except Exception as e:
            print(f"Update art failed: {e}")
            pass

    def async_process_background(self, img, w, h, r):
        try:
            if not getattr(self, 'ambilight_enabled', True):
                self.after(0, self.apply_glow_bg, None)
                return

            # --- Adaptive Ambilight Phase 1 ---
            # Resize image to 1x1 to find the average DOMINANT color.
            img_mini = img.resize((1, 1), Image.Resampling.LANCZOS)
            dominant_rgb = img_mini.getpixel((0, 0))
            if len(dominant_rgb) > 3: dominant_rgb = dominant_rgb[:3] # Handle RGBA
            
            # Darken this color by 80% (multiply RGB by 0.2)
            darkened_rgb = tuple(int(c * 0.2) for c in dominant_rgb)
            hex_color = '#{:02x}{:02x}{:02x}'.format(*darkened_rgb)
            
            # Apply this color to the window background (or acrylic tint)
            # Update the solid background fallback color
            self.island_color = hex_color
            
            img_copy = img.copy()
            glow = self.create_glow_background(img_copy, w, h, r)
            self.after(0, self.apply_glow_bg, glow)
        except Exception as e:
            print(f"Async glow error: {e}")
            self.after(0, self.apply_glow_bg, None)

    def create_glow_background(self, img, w, h, r):
        """Create a blurred ambilight background and blend with pure black based on intensity."""
        from PIL import ImageFilter, ImageDraw, ImageEnhance
        
        # Resize album art to fill the background
        img_resized = img.resize((w, h), Image.Resampling.LANCZOS)
       
        # Apply heavy blur for glow effect
        blurred = img_resized.filter(ImageFilter.GaussianBlur(radius=50))
        
        # Reduce brightness to ensure text readability even at 100%
        # Cap maximum brightness at 70% of original to prevent washing out text
        intensity = getattr(self, 'ambilight_intensity', 0.7)
        max_brightness = 0.7  # Never go above 70% brightness
        brightness_factor = intensity * max_brightness
        
        enhancer = ImageEnhance.Brightness(blurred)
        dimmed_glow = enhancer.enhance(brightness_factor)
        
        # Create base pure black image
        base = Image.new("RGB", (w, h), "#000000")
        
        # Blend dimmed glow with black (this is now redundant but kept for smoothness)
        blended = Image.blend(base, dimmed_glow, intensity)
        
        # Add a subtle darkening overlay in the text area (right 55% of widget)
        # This creates better contrast for text regardless of intensity
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        text_area_start = int(w * 0.40)  # Start slightly earlier to cover more text area
        # Create gradient from transparent to dark (increased opacity for readability)
        for i in range(text_area_start, w):
            # Gradual increase from 0 to 75% opacity (0 to 190 in 0-255 scale)
            opacity = int(190 * ((i - text_area_start) / (w - text_area_start)))
            overlay_draw.rectangle([i, 0, i+1, h], fill=(0, 0, 0, opacity))
        
        blended_rgba = blended.convert("RGBA")
        blended_rgba = Image.alpha_composite(blended_rgba, overlay)
        
        # Create rounded mask
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([0, 0, w-1, h-1], radius=r, fill=255)
        
        # Create final result with rounded corners by compositing over transparent key color
        result = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        blended_rgba = blended.convert("RGBA")
        blended_rgba.putalpha(mask)
        
        # Composite the masked glow over the window's transparency key color
        # This ensures the corners outside the mask become transparent
        bg_color = getattr(self, 'bg_key', "#000001")
        if bg_color.startswith('#'):
             # Parse hex manually if needed, or use Image.new support
             pass
             
        final = Image.new("RGB", (w, h), bg_color)
        final.paste(blended_rgba, (0, 0), blended_rgba)
        
        return final

    def fade_text(self, item_id, new_text):
        """Pure vertical scroll transition without color flicker."""
        if not hasattr(self, 'fade_targets'): self.fade_targets = {}
        
        # If we are already animating to this exact text, DO NOT restart the animation
        # (This prevents flickering during rapid updates)
        if self.fade_targets.get(item_id) == new_text:
            return
            
        current_text = self.canvas.itemcget(item_id, "text")
        if current_text == new_text: 
            return
        
        # New target text
        self.fade_targets[item_id] = new_text
        
        if not hasattr(self, 'fade_jobs'): self.fade_jobs = {}
        prop_dy = "title_dy" if item_id == self.title_id else "artist_dy"
        
        if item_id in self.fade_jobs:
            self.after_cancel(self.fade_jobs[item_id])
            
        steps = 8
        delay = 12 # Total ~200ms transition
        
        def animate(step, phase):
            t = step / steps
            
            if phase == 0:
                # Slide OUT (Up)
                setattr(self, prop_dy, -(10 * t))
                if step < steps:
                    self.fade_jobs[item_id] = self.after(delay, lambda: animate(step + 1, 0))
                else:
                    self.canvas.itemconfig(item_id, text=new_text)
                    # Sync Shadow Text
                    shadow_id = self.title_shadow_id if item_id == self.title_id else self.artist_shadow_id
                    self.canvas.itemconfig(shadow_id, text=new_text)
                    animate(0, 1)
            else:
                # Slide IN (Up from bottom)
                setattr(self, prop_dy, 10 - (10 * t))
                if step < steps:
                    self.fade_jobs[item_id] = self.after(delay, lambda: animate(step + 1, 1))
                else:
                    setattr(self, prop_dy, 0)
                    if item_id in self.fade_jobs: del self.fade_jobs[item_id]

        animate(0, 0)
            
if __name__ == "__main__":
    # --- Single Instance Check ---
    # Create a named mutex. If it already exists, GetLastError returns 183.
    mutex_name = "Local\\MediaIslandWidget_Unique_Lock_ULTRA_FINAL_V7"
    _app_mutex = None
    try:
        # CreateMutexW(security_attributes, initial_owner, name)
        _app_mutex = windll.kernel32.CreateMutexW(None, True, mutex_name)
        if windll.kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
            print("Media Island is already running.")
            sys.exit(0)
    except Exception as e:
        print(f"Warning: mutex check failed: {e}")

    app = MediaWidget()
    app._app_mutex = _app_mutex  # Store mutex handle for cleanup
    app.mainloop()
