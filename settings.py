import customtkinter as ctk
import json
import os
import sys
import subprocess
from ctypes import windll, byref, sizeof, c_int, c_long
import tkinter as tk

# --- Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# --- Constants ---
BG_COLOR = "#0A0A0A"        # Deepest Black
CARD_COLOR = "#141414"      # Subtle Card
ACCENT_COLOR = "#FFFFFF"    # Stark White
SUB_TEXT = "#666666"        # Dim Gray
HOVER_COLOR = "#1F1F1F"     # Interaction State

class StudioSlider(ctk.CTkFrame):
    """Premium slider with value readout"""
    def __init__(self, parent, label, from_, to, initial_val, callback, step=None):
        super().__init__(parent, fg_color="transparent")
        self.callback = callback
        self.step = step
        
        # Header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, 5))
        
        lbl = ctk.CTkLabel(head, text=label, font=("Segoe UI Variable Display", 13), text_color="#E0E0E0")
        lbl.pack(side="left")
        
        self.val_lbl = ctk.CTkLabel(head, text=str(int(initial_val)), font=("Segoe UI Variable Display", 13, "bold"), text_color="#FFFFFF")
        self.val_lbl.pack(side="right")
        
        # Slider
        steps = int((to - from_)/step) if step else 100
        self.slider = ctk.CTkSlider(
            self, 
            from_=from_, 
            to=to, 
            number_of_steps=steps,
            command=self._on_change,
            fg_color="#333333",
            progress_color="#FFFFFF",
            button_color="#FFFFFF",
            button_hover_color="#DDDDDD",
            height=16
        )
        self.slider.set(initial_val)
        self.slider.pack(fill="x")
        
    def _on_change(self, val):
        v = int(val) if self.step and self.step >= 1 else round(val, 2)
        self.val_lbl.configure(text=str(v))
        self.callback(v)

class StudioToggle(ctk.CTkFrame):
    """Minimalist toggle row - List Style with Status Text"""
    def __init__(self, parent, label, initial_val, callback):
        super().__init__(parent, fg_color="transparent")
        self.callback = callback
        
        # Content Container
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="x", pady=10, padx=5)
        
        lbl = ctk.CTkLabel(container, text=label, font=("Segoe UI Variable Display", 13), text_color="#E0E0E0")
        lbl.pack(side="left")
        
        # Status Label (dynamic)
        self.status_lbl = ctk.CTkLabel(container, text="ON" if initial_val else "OFF", 
                                       font=("Segoe UI Variable Display", 11, "bold"), 
                                       text_color="#FFFFFF" if initial_val else "#666666")
        self.status_lbl.pack(side="right", padx=(10, 0))

        self.sw = ctk.CTkSwitch(
            container, 
            text="", 
            command=self._on_change,
            fg_color="#333333",
            progress_color="#FFFFFF",
            button_color="#FFFFFF",
            button_hover_color="#DDDDDD",
            width=40, height=20, switch_height=16, switch_width=16
        )
        if initial_val: self.sw.select()
        self.sw.pack(side="right")
        
        # Separator Line
        sep = ctk.CTkFrame(self, height=1, fg_color="#1F1F1F")
        sep.pack(fill="x", side="bottom")

    def _on_change(self):
        val = bool(self.sw.get())
        self.status_lbl.configure(text="ON" if val else "OFF", text_color="#FFFFFF" if val else "#666666")
        self.callback(val)

class SettingsApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Window Setup
        self.overrideredirect(True) # Frameless
        self.geometry("540x800")
        self.configure(fg_color=BG_COLOR)
        self.title("Config Studio")
        
        # Center Window
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - 540) // 2
        y = (screen_h - 800) // 2
        self.geometry(f"+{x}+{y}")
        
        # Native DWM Shadow & Rounded Corners
        try:
            hwnd = windll.user32.GetParent(self.winfo_id())
            # DWMWA_WINDOW_CORNER_PREFERENCE = 33, Round = 2
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, byref(c_int(2)), sizeof(c_int))
            # DWMWA_BORDER_COLOR = 34
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, byref(c_int(0x00333333)), sizeof(c_int))
        except: pass
        
        self.config_path = "config.json"
        self.load_config()
        self.setup_ui()
        
    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    self.config = json.load(f)
            except: self.config = {}
        else:
            self.config = {}
        # Ensure Defaults
        defaults = {
            "mode": "island",
            "island_width": 550, "island_height": 140, "island_border_radius": 45,
            "normal_geometry": "500x125+100+100", "normal_border_radius": 15,
            "show_title": True, "show_controls": True,
            "animation_speed": 0.2, "stiffness": 550, "damping": 38,
            "ambilight_intensity": 70  # Default 70% blend
        }
        for k,v in defaults.items():
            if k not in self.config: self.config[k] = v

    def save_config(self):
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=4)

    def setup_ui(self):
        # --- Custom Title Bar ---
        self.title_bar = ctk.CTkFrame(self, fg_color="transparent", height=40)
        self.title_bar.pack(fill="x", pady=5)
        self.title_bar.bind("<Button-1>", self.start_drag)
        self.title_bar.bind("<B1-Motion>", self.do_drag)
        
        lbl = ctk.CTkLabel(self.title_bar, text="CONFIG STUDIO", font=("Segoe UI Variable Display", 12, "bold"), text_color=SUB_TEXT)
        lbl.pack(side="left", padx=20)
        lbl.bind("<Button-1>", self.start_drag)
        
        close_btn = ctk.CTkButton(
            self.title_bar, text="✕", width=30, height=30, 
            fg_color="transparent", hover_color="#C42B1C", text_color="white",
            font=("Arial", 14), command=self.close_app
        )
        close_btn.pack(side="right", padx=10)
        
        # --- Tab Navigation ---
        self.tabs = ctk.CTkSegmentedButton(
            self,
            values=["General", "Island", "Normal"],
            command=self.switch_tab,
            fg_color=CARD_COLOR,
            selected_color="#333333",
            selected_hover_color="#444444",
            unselected_color=CARD_COLOR,
            unselected_hover_color="#222222",
            text_color="#FFFFFF",
            font=("Segoe UI Variable Display", 13, "bold"),
            height=32
        )
        self.tabs.pack(fill="x", padx=20, pady=(10, 5))
        self.tabs.set("General")
        
        # --- Scrollable Content ---
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.build_general_view()
        
        # --- Footer ---
        apply_btn = ctk.CTkButton(
            self, text="APPLY & CLOSE", height=45, corner_radius=8,
            fg_color="#FFFFFF", text_color="#000000", hover_color="#DDDDDD",
            font=("Segoe UI Variable Display", 13, "bold"),
            command=self.close_app
        )
        apply_btn.pack(fill="x", padx=20, pady=(0, 20))

    def switch_tab(self, value):
        # Clear current scroll content
        for widget in self.scroll.winfo_children():
            widget.destroy()
            
        if value == "General":
            self.build_general_view()
        elif value == "Island":
            self.build_island_view()
        elif value == "Normal":
            self.build_normal_view()

    def build_general_view(self):
        # --- Section: Appearance ---
        self.add_header("Appearance")
        self.add_toggle("Show Song Title", "show_title")
        self.add_toggle("Show Artist Name", "show_artist")
        self.add_toggle("Show Media Controls", "show_controls")
        self.add_toggle("Show Progress Bar", "show_progress")
        self.add_toggle("Adaptive Ambilight", "ambilight_enabled")
        
        # Ambilight Intensity
        amb_frame = ctk.CTkFrame(self.scroll, fg_color=CARD_COLOR, corner_radius=12)
        amb_frame.pack(fill="x", pady=5)
        inner_amb = ctk.CTkFrame(amb_frame, fg_color="transparent")
        inner_amb.pack(fill="x", padx=15, pady=15)
        self.add_slider(inner_amb, "Ambilight Intensity (%)", 0, 100, "ambilight_intensity", step=5)
        
        # --- Section: Physics (Pro) ---
        self.add_header("Animation Physics")
        phys_frame = ctk.CTkFrame(self.scroll, fg_color=CARD_COLOR, corner_radius=12)
        phys_frame.pack(fill="x", pady=5)
        inner = ctk.CTkFrame(phys_frame, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=15)
        
        self.add_slider(inner, "Bounce (Stiffness)", 100, 1000, "stiffness", step=10)
        self.add_spacer(inner)
        self.add_slider(inner, "Friction (Damping)", 10, 100, "damping", step=1)
        
        self.add_header("System")
        sys_frame = ctk.CTkFrame(self.scroll, fg_color=CARD_COLOR, corner_radius=12)
        sys_frame.pack(fill="x", pady=5)
        inner_s = ctk.CTkFrame(sys_frame, fg_color="transparent")
        inner_s.pack(fill="x", padx=15, pady=15)
        self.add_slider(inner_s, "Animation Speed", 0.05, 0.5, "animation_speed", step=0.05)

    def build_island_view(self):
        self.add_header("Island Dimensions")
        
        dims_frame = ctk.CTkFrame(self.scroll, fg_color=CARD_COLOR, corner_radius=12)
        dims_frame.pack(fill="x", pady=5)
        
        inner = ctk.CTkFrame(dims_frame, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=15)
        
        self.add_slider(inner, "Island Width", 300, 800, "island_width", step=10)
        self.add_spacer(inner)
        self.add_slider(inner, "Island Height", 80, 250, "island_height", step=5)
        self.add_spacer(inner)
        self.add_slider(inner, "Corner Radius", 0, 80, "island_border_radius", step=1)

    def build_normal_view(self):
        self.add_header("Normal Dimensions")
        
        dims_frame = ctk.CTkFrame(self.scroll, fg_color=CARD_COLOR, corner_radius=12)
        dims_frame.pack(fill="x", pady=5)
        
        inner = ctk.CTkFrame(dims_frame, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=15)
        
        # Parse Normal Geometry
        try:
            geom = self.config.get("normal_geometry", "500x125+100+100")
            parts = geom.replace('x', '+').split('+')
            w, h = int(parts[0]), int(parts[1])
        except: w, h = 500, 125
        
        def update_w(val):
            self.update_normal_geom(w=int(val))
        def update_h(val):
            self.update_normal_geom(h=int(val))
            
        self.add_raw_slider(inner, "Widget Width", 300, 1000, w, update_w, step=10)
        self.add_spacer(inner)
        self.add_raw_slider(inner, "Widget Height", 100, 400, h, update_h, step=5)
        self.add_spacer(inner)
        self.add_slider(inner, "Corner Radius", 0, 80, "normal_border_radius", step=1)
        
        self.add_header("Info")
        info = ctk.CTkLabel(self.scroll, text="Position is saved automatically when you drag the widget.", 
                           font=("Segoe UI Variable Text", 11), text_color=SUB_TEXT, justify="left")
        info.pack(anchor="w", padx=10)

    def update_normal_geom(self, w=None, h=None):
        geom = self.config.get("normal_geometry", "500x125+100+100")
        try:
            parts = geom.replace('x', '+').split('+')
            old_w, old_h, x, y = parts[0], parts[1], parts[2], parts[3]
        except:
             old_w, old_h, x, y = 500, 125, 100, 100
             
        new_w = w if w is not None else old_w
        new_h = h if h is not None else old_h
        self.config["normal_geometry"] = f"{new_w}x{new_h}+{x}+{y}"
        self.save_config()

    # --- UI Helpers ---

    # --- UI Helpers ---
    def add_header(self, text):
        lbl = ctk.CTkLabel(self.scroll, text=text.upper(), font=("Segoe UI Variable Display", 11, "bold"), text_color=SUB_TEXT)
        lbl.pack(anchor="w", pady=(20, 5), padx=5)

    def add_toggle(self, label, key):
        def cb(val):
            self.config[key] = val
            self.save_config()
        StudioToggle(self.scroll, label, self.config.get(key, True), cb).pack(fill="x", pady=4)

    def add_slider(self, parent, label, from_, to, key, step=1):
        def cb(val):
            self.config[key] = val
            self.save_config()
        StudioSlider(parent, label, from_, to, self.config.get(key, from_), cb, step=step).pack(fill="x")

    def add_raw_slider(self, parent, label, from_, to, current, callback, step=1):
        StudioSlider(parent, label, from_, to, current, callback, step=step).pack(fill="x")

    def add_spacer(self, parent):
        ctk.CTkFrame(parent, fg_color="transparent", height=15).pack()

    # --- Window Logic ---
    def start_drag(self, event):
        self.x_offset = event.x
        self.y_offset = event.y

    def do_drag(self, event):
        x = self.winfo_x() + (event.x - self.x_offset)
        y = self.winfo_y() + (event.y - self.y_offset)
        self.geometry(f"+{x}+{y}")

    def close_app(self):
        self.save_config()
        self.destroy()

if __name__ == "__main__":
    app = SettingsApp()
    app.mainloop()
