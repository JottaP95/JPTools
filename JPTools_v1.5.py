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

PROCESS_NAME = 'ragexe.exe'
HP_ADDRESS = 21628764
MAX_HP_ADDRESS = 21628768
USE_KEY = 'R'
POT_THRESHOLD = 0.9  # 90%

# === FUNÇÕES DE ENVIO DE TECLAS E CLIQUE ===

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

# === PEGAR HWND DO PROCESSO ===

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

# === AUTOPOT ===

class AutoPot(threading.Thread):
    def __init__(self, pm, hwnd, use_key=USE_KEY, threshold=POT_THRESHOLD):
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

# === TOOLTIP ===

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

# === TRISTATE CHECKBOX ===

class TriStateCheckbox(tk.Label):
    STATES = [" ", "–", "✔"]
    TOOLTIP_TEXTS = [
        "Desativado: não spama esta tecla",
        "Skillspam + clique",
        "Spam somente tecla"
    ]

    def __init__(self, master, key_name, **kwargs):
        super().__init__(master, text=" ", relief="ridge", width=2, font=("Arial", 14), **kwargs)
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

# === KEY WIDGET (LABEL + TRISTATE CHECKBOX) ===

class KeyWidget(tk.Frame):
    def __init__(self, master, key_name):
        super().__init__(master, relief="flat", bd=1)
        self.key_name = key_name.upper()
        self.checkbox = TriStateCheckbox(self, key_name)
        self.checkbox.pack(side="right")
        self.label = tk.Label(self, text=self.key_name, font=("Arial", 12), width=3)
        self.label.pack(side="left")

    def get_state(self):
        return self.checkbox.get_state()

# === KEY SELECTOR ===

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
            kw.grid(row=row, column=col, padx=3, pady=3)
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

# === SKILLSPAM ===

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

# === APLICATIVO PRINCIPAL ===

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Autopot + Skillspam Ragnarok")
        self.geometry("480x380")
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

        self.create_widgets()

        signal.signal(signal.SIGINT, self.signal_handler)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_widgets(self):
        ap_frame = ttk.LabelFrame(self, text="Autopot")
        ap_frame.pack(fill='x', padx=10, pady=10)

        self.ap_button = ttk.Button(ap_frame, text="Ligar Autopot", command=self.toggle_autopot)
        self.ap_button.pack(padx=5, pady=5)

        ss_frame = ttk.LabelFrame(self, text="Skillspam (Clique nos símbolos para alterar o estado)")
        ss_frame.pack(fill='both', expand=True, padx=10, pady=10)

        self.key_selector = KeySelector(ss_frame)
        self.key_selector.pack()

        self.ss_button = ttk.Button(ss_frame, text="Ligar Skillspam", command=self.toggle_skillspam)
        self.ss_button.pack(pady=5)

        self.info_label = ttk.Label(self, text="Estados:\n"
                                               "' ' (vazio) = Desativado\n"
                                               "'–' = Skillspam + clique\n"
                                               "'✔' = Spam somente tecla\n"
                                               "Pressione as teclas no teclado para executar o spam.\n"
                                               "Feche a janela ou Ctrl+C para sair.",
                                    foreground="blue")
        self.info_label.pack(pady=5)

    def toggle_autopot(self):
        if self.autopot and self.autopot.running.is_set():
            self.autopot.stop()
            self.autopot.join()
            self.ap_button.config(text="Ligar Autopot")
        elif self.autopot:
            self.autopot = AutoPot(self.pm, self.hwnd, use_key=USE_KEY, threshold=POT_THRESHOLD)
            self.autopot.start()
            self.ap_button.config(text="Desligar Autopot")
        else:
            print("[ERRO] Autopot não iniciado (PM ou HWND faltando)")

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