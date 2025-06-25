import time
import threading
import pymem
import win32gui
import win32api
import win32con
import win32process
import tkinter as tk
from tkinter import ttk
import keyboard
import signal
import sys
import winsound

PROCESS_NAME = 'ragexe.exe'
HP_ADDRESS = 21628764
MAX_HP_ADDRESS = 21628768
DEFAULT_USE_KEY = 'R'
POT_THRESHOLD = 0.9  # 90%

def SendMessage(hwnd, msg, wparam, lparam, flags=win32con.SMTO_ABORTIFHUNG, timeout=5000):
    return win32gui.SendMessageTimeout(hwnd, msg, wparam, lparam, flags, timeout)

def SendKey(hwnd, key: str) -> None:
    char_code = ord(key)
    vk_code = win32api.VkKeyScan(key) & 0xFF
    scan_code = win32api.MapVirtualKey(vk_code, 0)
    lparamdown = (scan_code << 16) | 1
    lparamup = (1 << 31) | (1 << 30) | (scan_code << 16) | 1

    try:
        SendMessage(hwnd, win32con.WM_KEYDOWN, vk_code, lparamdown)
        SendMessage(hwnd, win32con.WM_CHAR, char_code, lparamdown)
        SendMessage(hwnd, win32con.WM_KEYUP, vk_code, lparamup)
    except Exception as e:
        print(f"[ERRO] Falha ao enviar tecla: {e}")

def SendClick(hwnd, x=0, y=0) -> None:
    SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, 0)
    SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, 0)

def get_hwnd_from_pid(pid):
    hwnds = []
    def enum_windows_proc(hwnd, lParam):
        if win32gui.IsWindowVisible(hwnd):
            _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
            if window_pid == pid:
                hwnds.append(hwnd)
        return True
    win32gui.EnumWindows(enum_windows_proc, None)
    return hwnds[0] if hwnds else None

class AutoPot(threading.Thread):
    def __init__(self, pm, hwnd, use_key=DEFAULT_USE_KEY, threshold=POT_THRESHOLD):
        super().__init__()
        self.pm = pm
        self.hwnd = hwnd
        self.use_key = use_key
        self.threshold = threshold
        self.running = threading.Event()
        self.daemon = True

    def run(self):
        self.running.set()
        while self.running.is_set():
            try:
                hp = self.pm.read_int(HP_ADDRESS)
                max_hp = self.pm.read_int(MAX_HP_ADDRESS)
                if max_hp == 0:
                    time.sleep(0.1)
                    continue
                hp_percent = hp / max_hp
                if hp_percent < self.threshold:
                    SendKey(self.hwnd, self.use_key)
                time.sleep(0.2)
            except Exception as e:
                print(f"[ERRO autopot] {e}")
                break

    def stop(self):
        self.running.clear()

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tipwindow or not self.text:
            return
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

class TriStateCheckbox(tk.Label):
    STATES = [" ", "✔", "–"]  # ✔ = spam+click, – = somente spam tecla
    TOOLTIP_TEXTS = [
        "Desativado: não spama esta tecla",
        "Skillspam + clique",
        "Spam somente tecla"
    ]

    def __init__(self, master, key_name, **kwargs):
        super().__init__(master, text=" ", relief="ridge", width=1, font=("Arial", 10), **kwargs)
        self.state = 0
        self.key_name = key_name.lower()
        self.bind("<Button-1>", self.toggle_state)
        self.update_display()
        self.tooltip = ToolTip(self, self.TOOLTIP_TEXTS[self.state])

    def toggle_state(self, event=None):
        self.state = (self.state + 1) % 3
        self.update_display()
        self.tooltip.text = self.TOOLTIP_TEXTS[self.state]

    def update_display(self):
        self.config(text=self.STATES[self.state])

    def get_state(self):
        return self.state

class KeyWidget(tk.Frame):
    def __init__(self, master, key_name):
        super().__init__(master, relief="flat", bd=1)
        self.key_name = key_name.upper()
        self.checkbox = TriStateCheckbox(self, key_name)
        self.checkbox.pack(side="right", padx=(1, 0))
        self.label = tk.Label(self, text=self.key_name, font=("Arial", 9), width=2)
        self.label.pack(side="left")

    def get_state(self):
        return self.checkbox.get_state()

class KeySelector(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.key_widgets = []
        self.key_states = {}
        self.create_widgets()

    def create_widgets(self):
        keys_order = [
            '1','2','3','4','5','6','7','8','9','0',
            'Q','W','E','R','T','Y','U','I','O','P',
            'A','S','D','F','G','H','J','K','L',
            'Z','X','C','V','B','N','M'
        ]

        row, col = 0, 0
        for k in keys_order:
            kw = KeyWidget(self, k)
            kw.grid(row=row, column=col, padx=1, pady=1)
            self.key_widgets.append(kw)
            self.key_states[k.lower()] = 0
            col += 1
            if col >= 10:
                col = 0
                row += 1

    def get_key_states(self):
        for kw in self.key_widgets:
            self.key_states[kw.key_name.lower()] = kw.get_state()
        return self.key_states

class SkillSpam(threading.Thread):
    def __init__(self, hwnd, key_selector: KeySelector):
        super().__init__()
        self.hwnd = hwnd
        self.key_selector = key_selector
        self.running = threading.Event()
        self.daemon = True

    def run(self):
        self.running.set()
        while self.running.is_set():
            key_states = self.key_selector.get_key_states()
            for key, state in key_states.items():
                if state == 0:
                    continue
                if keyboard.is_pressed(key):
                    if state == 1:
                        self.send_key_and_click(key)
                    elif state == 2:
                        self.send_key_only(key)
                    time.sleep(0.02)
            time.sleep(0.01)

    def send_key_and_click(self, key):
        SendKey(self.hwnd, key)
        SendClick(self.hwnd)

    def send_key_only(self, key):
        SendKey(self.hwnd, key)

    def stop(self):
        self.running.clear()

def play_toggle_sound(on=True):
    freq = 1000 if on else 600
    dur = 150
    winsound.Beep(freq, dur)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JPTools v2.0 by J O T T A")
        self.geometry("450x370")
        self.resizable(False, False)

        try:
            self.pm = pymem.Pymem(PROCESS_NAME)
            self.hwnd = get_hwnd_from_pid(self.pm.process_id)
            if not self.hwnd:
                print("[ERRO] Janela do processo não encontrada.")
        except Exception as e:
            print(f"[ERRO] Falha ao conectar ao processo: {e}")

        self.autopot = AutoPot(self.pm, self.hwnd) if hasattr(self, 'pm') and self.hwnd else None
        self.skillspam = None
        self.registered_hotkeys = []

        self.create_widgets()

        signal.signal(signal.SIGINT, self.signal_handler)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.register_hotkeys()

    def create_widgets(self):
        ap_frame = ttk.LabelFrame(self, text="Autopot")
        ap_frame.pack(fill='x', padx=10, pady=5)

        self.ap_button = ttk.Button(ap_frame, text="Ligar Autopot", command=self.toggle_autopot)
        self.ap_button.pack(padx=5, pady=5)
        ToolTip(self.ap_button, "Liga ou desliga o autopot")

        ap_key_frame = ttk.Frame(ap_frame)
        ap_key_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(ap_key_frame, text="Tecla do Autopot:").pack(side="left")
        self.autopot_key_entry = ttk.Entry(ap_key_frame, width=5)
        self.autopot_key_entry.insert(0, DEFAULT_USE_KEY)
        self.autopot_key_entry.pack(side="left", padx=5)
        ToolTip(self.autopot_key_entry, "Tecla que o autopot irá usar para ativar a poção")

        ap_threshold_frame = ttk.Frame(ap_frame)
        ap_threshold_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(ap_threshold_frame, text="HP % para usar poção:").pack(side="left")
        self.hp_threshold_entry = ttk.Entry(ap_threshold_frame, width=5)
        self.hp_threshold_entry.insert(0, str(int(POT_THRESHOLD * 100)))
        self.hp_threshold_entry.pack(side="left", padx=5)
        ToolTip(self.hp_threshold_entry, "Digite a porcentagem de HP para usar a poção (ex: 90 para 90%)")

        toggle_key_frame = ttk.Frame(self)
        toggle_key_frame.pack(fill='x', padx=10, pady=5)
        ttk.Label(toggle_key_frame, text="Atalho para ligar/desligar Autopot + Skillspam:").pack(side="left")
        self.toggle_key_entry = ttk.Entry(toggle_key_frame, width=10)
        self.toggle_key_entry.insert(0, "F1")
        self.toggle_key_entry.pack(side="left", padx=5)
        ToolTip(self.toggle_key_entry, "Tecla de atalho que liga ou desliga ambos, autopot e skillspam")

        ss_frame = ttk.LabelFrame(self, text="Skillspam (Clique nos símbolos para alterar o estado)")
        ss_frame.pack(fill='both', expand=True, padx=10, pady=10)

        self.key_selector = KeySelector(ss_frame)
        self.key_selector.pack()
        ToolTip(self.key_selector, "Clique nos símbolos para definir o tipo de spam para cada tecla")

        self.ss_button = ttk.Button(ss_frame, text="Ligar Skillspam", command=self.toggle_skillspam)
        self.ss_button.pack(pady=5)
        ToolTip(self.ss_button, "Liga ou desliga o skillspam")

        self.info_label = ttk.Label(self, text="Ta em BETA!! Qualquer erro, procure outro ;)",
                                    foreground="blue", font=("Arial", 9))
        self.info_label.pack(pady=5)

    def get_hp_threshold(self):
        try:
            val = int(self.hp_threshold_entry.get())
            if 1 <= val <= 100:
                return val / 100
        except:
            pass
        return POT_THRESHOLD

    def register_hotkeys(self):
        for hk in self.registered_hotkeys:
            try:
                keyboard.remove_hotkey(hk)
            except Exception:
                pass
        self.registered_hotkeys.clear()

        def on_toggle_all():
            autopot_running = self.autopot and self.autopot.running.is_set()
            skillspam_running = self.skillspam and self.skillspam.running.is_set()

            if autopot_running or skillspam_running:
                if autopot_running:
                    self.autopot.stop()
                    self.autopot.join()
                    self.ap_button.config(text="Ligar Autopot")
                if skillspam_running:
                    self.skillspam.stop()
                    self.skillspam.join()
                    self.ss_button.config(text="Ligar Skillspam")
                    self.skillspam = None
                play_toggle_sound(False)
            else:
                use_key = self.autopot_key_entry.get().strip()
                if not use_key:
                    use_key = DEFAULT_USE_KEY
                threshold = self.get_hp_threshold()
                if not self.autopot or not self.autopot.running.is_set():
                    self.autopot = AutoPot(self.pm, self.hwnd, use_key=use_key, threshold=threshold)
                    self.autopot.start()
                    self.ap_button.config(text="Desligar Autopot")
                if not self.skillspam and self.hwnd:
                    self.skillspam = SkillSpam(self.hwnd, self.key_selector)
                    self.skillspam.start()
                    self.ss_button.config(text="Desligar Skillspam")
                play_toggle_sound(True)

        try:
            hotkey = self.toggle_key_entry.get()
            hk = keyboard.add_hotkey(hotkey, on_toggle_all)
            self.registered_hotkeys.append(hk)
        except Exception as e:
            print(f"[ERRO] Não foi possível registrar hotkey: {e}")

    def toggle_autopot(self):
        if self.autopot and self.autopot.running.is_set():
            self.autopot.stop()
            self.autopot.join()
            self.ap_button.config(text="Ligar Autopot")
        else:
            use_key = self.autopot_key_entry.get().strip()
            if not use_key:
                use_key = DEFAULT_USE_KEY
            threshold = self.get_hp_threshold()
            self.autopot = AutoPot(self.pm, self.hwnd, use_key=use_key, threshold=threshold)
            self.autopot.start()
            self.ap_button.config(text="Desligar Autopot")

    def toggle_skillspam(self):
        if self.skillspam and self.skillspam.running.is_set():
            self.skillspam.stop()
            self.skillspam.join()
            self.ss_button.config(text="Ligar Skillspam")
            self.skillspam = None
        elif self.hwnd:
            self.skillspam = SkillSpam(self.hwnd, self.key_selector)
            self.skillspam.start()
            self.ss_button.config(text="Desligar Skillspam")
        else:
            self.info_label.config(text="Erro: janela do jogo não encontrada.", foreground="red")

    def on_close(self):
        print("[INFO] Fechando aplicação...")
        self.cleanup()
        self.destroy()

    def cleanup(self):
        if self.autopot and self.autopot.running.is_set():
            self.autopot.stop()
            self.autopot.join()
        if self.skillspam and self.skillspam.running.is_set():
            self.skillspam.stop()
            self.skillspam.join()

    def signal_handler(self, sig, frame):
        print("\n[INFO] Ctrl+C detectado! Encerrando...")
        self.cleanup()
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    app = App()
    app.mainloop()
