import time
import threading
import win32gui
import win32api
import win32con
import win32process
import tkinter as tk
from tkinter import ttk, messagebox
import keyboard
import signal
import sys
import winsound
import pymem
import pymem.process
import ctypes
import numpy as np
import queue

# --- FUNÇÕES DE ENVIO DE COMANDO (LÓGICA INTACTA) ---

def SendMessage(hwnd, msg, wparam, lparam, flags=win32con.SMTO_ABORTIFHUNG, timeout=5000):
    return win32gui.SendMessageTimeout(hwnd, msg, wparam, lparam, flags, timeout)

def SendKey(hwnd, key: str) -> None:
    try:
        char_code = ord(key.upper())
        vk_code = win32api.VkKeyScan(key.upper()) & 0xFF
        scan_code = win32api.MapVirtualKey(vk_code, 0)
        lparamdown = (scan_code << 16) | 1
        lparamup = (1 << 31) | (1 << 30) | (scan_code << 16) | 1
        
        SendMessage(hwnd, win32con.WM_KEYDOWN, vk_code, lparamdown)
        SendMessage(hwnd, win32con.WM_CHAR, char_code, lparamdown)
        time.sleep(0.02)
        SendMessage(hwnd, win32con.WM_KEYUP, vk_code, lparamup)
    except Exception as e:
        print(f"[ERRO] Falha ao enviar tecla: {e}")

def SendClick(hwnd):
    SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, 0)
    time.sleep(0.02)
    SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, 0)

def get_hwnd_from_pid(pid):
    hwnds = []
    def enum_windows_proc(hwnd, lParam):
        if win32gui.IsWindowVisible(hwnd):
            _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
            if window_pid == pid: hwnds.append(hwnd)
        return True
    win32gui.EnumWindows(enum_windows_proc, None)
    return hwnds[0] if hwnds else None

# --- CLASSES DO BOT (LÓGICA INTACTA) ---

class AutoPot(threading.Thread):
    def __init__(self, pm, hwnd, hp_address, max_hp_address, use_key, threshold):
        super().__init__(); self.pm = pm; self.hwnd = hwnd
        self.hp_address = hp_address; self.max_hp_address = max_hp_address
        self.use_key = use_key; self.threshold = threshold
        self.running = threading.Event(); self.daemon = True
    def run(self):
        self.running.set(); print(f"AutoPot iniciado. Lendo HP de 0x{self.hp_address:X}")
        while self.running.is_set():
            try:
                hp = self.pm.read_int(self.hp_address); max_hp = self.pm.read_int(self.max_hp_address)
                if max_hp > 0 and hp > 0:
                    if (hp / max_hp) < self.threshold:
                        SendKey(self.hwnd, self.use_key); time.sleep(0.3)
                time.sleep(0.1)
            except Exception: self.stop()
    def stop(self): self.running.clear()

class SkillSpam(threading.Thread):
    def __init__(self, hwnd, key_selector):
        super().__init__(); self.hwnd = hwnd; self.key_selector = key_selector
        self.running = threading.Event(); self.daemon = True
    def run(self):
        self.running.set(); print("SkillSpam iniciado.")
        while self.running.is_set():
            key_states = self.key_selector.get_key_states()
            for key, state in key_states.items():
                if state > 0 and keyboard.is_pressed(key):
                    if state == 1: self.send_key_and_click(key)
                    elif state == 2: self.send_key_only(key)
                    time.sleep(0.02)
            time.sleep(0.01)
    def send_key_and_click(self, key): SendKey(self.hwnd, key); SendClick(self.hwnd)
    def send_key_only(self, key): SendKey(self.hwnd, key)
    def stop(self): self.running.clear()

# --- CLASSES DA INTERFACE (COM ESTILO MELHORADO) ---
class ToolTip:
    def __init__(self, widget, text, bg_color, text_color):
        self.widget = widget; self.text = text; self.tipwindow = None
        self.bg_color = bg_color; self.text_color = text_color
        widget.bind("<Enter>", self.show_tip); widget.bind("<Leave>", self.hide_tip)
    def show_tip(self, event=None):
        if self.tipwindow or not self.text: return
        x, y, _, _ = self.widget.bbox("insert"); x += self.widget.winfo_rootx() + 25; y += self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget); tw.wm_overrideredirect(True); tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, justify='left', background=self.bg_color, fg=self.text_color, relief='solid', borderwidth=1, font=("Segoe UI", 8, "normal")).pack(ipadx=1)
    def hide_tip(self, event=None):
        if self.tipwindow: self.tipwindow.destroy(); self.tipwindow = None

class TriStateCheckbox(tk.Label):
    STATES = [" ", "✔", "–"]; TOOLTIP_TEXTS = ["Desativado", "Skillspam + Clique", "Spam Somente Tecla"]
    def __init__(self, master, bg_color, text_color, **kwargs):
        super().__init__(master, text=" ", relief="solid", width=2, font=("Segoe UI", 10), borderwidth=1, **kwargs)
        self.config(bg=bg_color, fg=text_color, highlightbackground="#555555")
        self.state = 0; self.bind("<Button-1>", self.toggle_state)
        self.update_display(); self.tooltip = ToolTip(self, self.TOOLTIP_TEXTS[self.state], bg_color="#3c3c3c", text_color="#d4d4d4")
    def toggle_state(self, event=None):
        self.state = (self.state + 1) % 3; self.update_display(); self.tooltip.text = self.TOOLTIP_TEXTS[self.state]
    def update_display(self): self.config(text=self.STATES[self.state])
    def get_state(self): return self.state

class KeyWidget(tk.Frame):
    def __init__(self, master, key_name, bg_color, text_color):
        super().__init__(master, bg=bg_color)
        self.key_name = key_name.upper()
        # CORREÇÃO: Removido o argumento 'key_name' da chamada e os argumentos de cor passados por nome.
        self.checkbox = TriStateCheckbox(self, bg_color="#1e1e1e", text_color=text_color)
        self.checkbox.pack(side="right", padx=(2, 0))
        self.label = tk.Label(self, text=self.key_name, font=("Segoe UI", 9, "bold"), width=2, bg=bg_color, fg=text_color)
        self.label.pack(side="left")
    def get_state(self): return self.checkbox.get_state()

class KeySelector(tk.Frame):
    def __init__(self, master, bg_color, text_color):
        super().__init__(master, bg=bg_color)
        self.key_widgets = []; self.key_states = {}
        keys_order = ['1','2','3','4','5','6','7','8','9','0','Q','W','E','R','T','Y','U','I','O','P','A','S','D','F','G','H','J','K','L','Z','X','C','V','B','N','M']
        row, col = 0, 0
        for k in keys_order:
            kw = KeyWidget(self, k, bg_color=bg_color, text_color=text_color); kw.grid(row=row, column=col, padx=2, pady=3)
            self.key_widgets.append(kw); self.key_states[k.lower()] = 0
            col += 1;
            if col >= 10: col = 0; row += 1
    def get_key_states(self):
        for kw in self.key_widgets: self.key_states[kw.key_name.lower()] = kw.get_state()
        return self.key_states

# --- APLICAÇÃO PRINCIPAL ---
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        # --- Configurações de Cor e Fonte ---
        self.BG_COLOR = "#1e1e1e"; self.FRAME_COLOR = "#2d2d30"; self.TEXT_COLOR = "#cccccc"
        self.ACCENT_COLOR = "#0e639c"; self.ACCENT_HOVER = "#1177bb"; self.FONT_NAME = "Segoe UI"
        
        self.title("JPTools"); self.geometry("520x300"); self.resizable(False, False)
        self.configure(bg=self.BG_COLOR)

        self.setup_styles()

        # --- Variáveis de Estado (Lógica intacta) ---
        self.pm = None; self.hwnd = None; self.autopot = None; self.skillspam = None
        self.dynamic_hp_address = None; self.dynamic_max_hp_address = None
        self.registered_hotkey = None; self.monitoring_active = threading.Event()
        self.gui_queue = queue.Queue()

        try:
            self.pm = pymem.Pymem("Ragexe.exe"); self.hwnd = get_hwnd_from_pid(self.pm.process_id)
            self.module = pymem.process.module_from_name(self.pm.process_handle, "Ragexe.exe")
            self.base_address, self.module_size = self.module.lpBaseOfDll, self.module.SizeOfImage
            if not self.hwnd: raise Exception("Janela não encontrada")
        except Exception as e:
            messagebox.showerror("Erro de Conexão", f"Não foi possível conectar ao 'Ragexe.exe'.\nErro: {e}")
            self.destroy(); return

        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.on_close); signal.signal(signal.SIGINT, self.on_close)
        self.after(100, self.process_queue)

    def setup_styles(self):
        style = ttk.Style(self); style.theme_use('clam')
        style.configure('.', background=self.BG_COLOR, foreground=self.TEXT_COLOR, font=(self.FONT_NAME, 10))
        style.configure('TFrame', background=self.BG_COLOR)
        style.configure('TLabel', background=self.BG_COLOR, foreground=self.TEXT_COLOR)
        style.configure('TLabelFrame', background=self.BG_COLOR, bordercolor="#555555")
        style.configure('TLabelFrame.Label', background=self.BG_COLOR, foreground=self.TEXT_COLOR, font=(self.FONT_NAME, 11, 'bold'))
        style.configure('TButton', background=self.ACCENT_COLOR, foreground='white', font=(self.FONT_NAME, 10, 'bold'), borderwidth=0, focusthickness=0, padding=8)
        style.map('TButton', background=[('active', self.ACCENT_HOVER), ('disabled', '#555555')])
        style.configure('TEntry', fieldbackground='#3c3c3c', foreground=self.TEXT_COLOR, bordercolor="#555555", insertcolor=self.TEXT_COLOR)
        style.configure('blue.Horizontal.TProgressbar', background=self.ACCENT_COLOR, troughcolor=self.FRAME_COLOR, bordercolor=self.FRAME_COLOR)
        style.configure('TNotebook', background=self.BG_COLOR, borderwidth=0)
        style.configure('TNotebook.Tab', background=self.FRAME_COLOR, foreground=self.TEXT_COLOR, padding=[10, 5], font=(self.FONT_NAME, 10, 'bold'), borderwidth=0)
        style.map('TNotebook.Tab', background=[('selected', self.ACCENT_COLOR)], foreground=[('selected', 'white')])

    def _read_memory(self, address, size):
        buffer = ctypes.create_string_buffer(size)
        ctypes.windll.kernel32.ReadProcessMemory(self.pm.process_handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(ctypes.c_size_t(0)))
        return buffer.raw

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding=10); main_frame.pack(fill="both", expand=True)
        self.calibration_frame = ttk.LabelFrame(main_frame, text="Calibração Automática do HP")
        self.calibration_frame.pack(fill="x", pady=(0, 10))
        instructions = "1. Digite seu HP atual.\n2. Clique em 'Iniciar Calibração'.\n3. Leve dano no jogo para o programa se auto-configurar."
        ttk.Label(self.calibration_frame, text=instructions, justify="left", font=(self.FONT_NAME, 9)).pack(pady=10, padx=10)
        calib_input_frame = ttk.Frame(self.calibration_frame); calib_input_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(calib_input_frame, text="Seu HP Atual:").pack(side="left")
        self.hp_value_var = tk.StringVar(); self.hp_entry = ttk.Entry(calib_input_frame, textvariable=self.hp_value_var, width=15)
        self.hp_entry.pack(side="left", padx=5)
        self.scan_button = ttk.Button(calib_input_frame, text="Iniciar Calibração", command=self.run_initial_scan_thread)
        self.scan_button.pack(side="left", padx=5)
        status_frame = ttk.Frame(self.calibration_frame); status_frame.pack(fill='x', expand=True, padx=10, pady=5)
        self.calib_status_var = tk.StringVar(value="Status: Aguardando calibração.")
        ttk.Label(status_frame, textvariable=self.calib_status_var, font=(self.FONT_NAME, 9)).pack(anchor='w')
        self.progress_bar = ttk.Progressbar(status_frame, style='blue.Horizontal.TProgressbar', orient="horizontal", mode="determinate")
        self.progress_bar.pack(pady=5, fill='x')
        self.controls_frame = ttk.Frame(self)

    def setup_bot_ui(self):
        self.calibration_frame.destroy()
        self.geometry("520x480")
        
        title_frame = ttk.Frame(self.controls_frame); title_frame.pack(fill='x', pady=10)
        ttk.Label(title_frame, text="JPTools Bot", font=(self.FONT_NAME, 16, 'bold')).pack(side="left")
        hotkey_frame = ttk.Frame(title_frame); hotkey_frame.pack(side='right')
        ttk.Label(hotkey_frame, text="Atalho Global:").pack(side="left")
        self.toggle_key_entry = ttk.Entry(hotkey_frame, width=8); self.toggle_key_entry.insert(0, "F1"); self.toggle_key_entry.pack(side="left", padx=5)

        notebook = ttk.Notebook(self.controls_frame, style='TNotebook')
        
        autopot_tab = ttk.Frame(notebook, padding=10)
        ttk.Label(autopot_tab, text="Tecla da Poção:").grid(row=0, column=0, padx=5, pady=10, sticky='w')
        self.autopot_key_entry = ttk.Entry(autopot_tab, width=10); self.autopot_key_entry.insert(0, "R"); self.autopot_key_entry.grid(row=0, column=1, padx=5, pady=10)
        ttk.Label(autopot_tab, text="Usar se HP < (%):").grid(row=1, column=0, padx=5, pady=10, sticky='w')
        self.hp_threshold_entry = ttk.Entry(autopot_tab, width=10); self.hp_threshold_entry.insert(0, "80"); self.hp_threshold_entry.grid(row=1, column=1, padx=5, pady=10)
        
        skillspam_tab = ttk.Frame(notebook, padding=10)
        self.key_selector = KeySelector(skillspam_tab, bg_color=self.FRAME_COLOR, text_color=self.TEXT_COLOR)
        self.key_selector.pack(expand=True, fill='both', padx=5, pady=5)
        
        notebook.add(autopot_tab, text=' AutoPot '); notebook.add(skillspam_tab, text=' SkillSpam ')
        notebook.pack(expand=True, fill="both", pady=5)
        
        self.controls_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        messagebox.showinfo("Calibração Concluída", f"Endereço de HP configurado: 0x{self.dynamic_hp_address:X}\n\nO bot está pronto!")
        self.register_hotkey()

    def run_initial_scan_thread(self):
        try: value = int(self.hp_value_var.get())
        except ValueError: messagebox.showerror("Erro", "Digite um valor de HP válido."); return
        self.scan_button.config(state="disabled", text="A Escanear...")
        threading.Thread(target=self.execute_initial_scan, args=(value,), daemon=True).start()

    def execute_initial_scan(self, value):
        self.monitoring_active.clear(); time.sleep(0.3)
        self.gui_queue.put(("status_update", "Status: Executando scan inicial..."))
        found_addrs = []; chunk_size = 4096 * 1024; total_scanned = 0
        for i in range(0, self.module_size, chunk_size):
            block = self._read_memory(self.base_address + i, min(chunk_size, self.module_size - i))
            arr = np.frombuffer(block, dtype=np.int32)
            matches = np.where(arr == value)[0]
            found_addrs.extend([int(self.base_address + i + (offset * 4)) for offset in matches])
            total_scanned += min(chunk_size, self.module_size - i)
            self.gui_queue.put(("progress", int((total_scanned / self.module_size) * 100)))
        self.gui_queue.put(("initial_scan_complete", (found_addrs, value)))

    def _thread_auto_monitor(self, addresses, initial_value):
        while self.monitoring_active.is_set():
            for addr in addresses:
                try:
                    current_val = self.pm.read_int(addr)
                    if current_val != initial_value and current_val > 0:
                        self.gui_queue.put(("address_found_auto", addr))
                        self.monitoring_active.clear(); return
                except: continue
            time.sleep(0.1)
            
    def process_queue(self):
        try:
            msg, data = self.gui_queue.get_nowait()
            if msg == "progress": self.progress_bar.config(value=data)
            elif msg == "status_update": self.calib_status_var.set(data)
            elif msg == "initial_scan_complete":
                addresses, value = data
                self.scan_button.config(state="normal", text="Iniciar Novo Scan")
                if not addresses:
                    self.calib_status_var.set(f"Status: Nenhum endereço encontrado para {value}. Tente novamente.")
                    return
                self.calib_status_var.set(f"Status: {len(addresses)} endereços na mira. Leve dano no jogo. Aguardando...")
                self.progress_bar.config(value=100); self.monitoring_active.set()
                threading.Thread(target=self._thread_auto_monitor, args=(addresses, value), daemon=True).start()
            elif msg == "address_found_auto":
                self.dynamic_hp_address = data
                self.dynamic_max_hp_address = data + 4
                self.setup_bot_ui()
        except queue.Empty: pass
        finally: self.after(100, self.process_queue)

    def on_toggle_all(self):
        is_running = self.autopot and self.autopot.running.is_set()
        if is_running:
            self.autopot.stop(); self.skillspam.stop(); winsound.Beep(600, 150); print("Tudo desligado.")
        else:
            try:
                pot_key = self.autopot_key_entry.get(); threshold = int(self.hp_threshold_entry.get()) / 100
                self.autopot = AutoPot(self.pm, self.hwnd, self.dynamic_hp_address, self.dynamic_max_hp_address, pot_key, threshold)
                self.skillspam = SkillSpam(self.hwnd, self.key_selector)
                self.autopot.start(); self.skillspam.start(); winsound.Beep(1000, 150); print("Tudo ligado.")
            except Exception as e: messagebox.showerror("Erro ao Iniciar", f"Verifique as configurações: {e}")

    def register_hotkey(self):
        if self.registered_hotkey: keyboard.remove_hotkey(self.registered_hotkey)
        try:
            hotkey_str = self.toggle_key_entry.get()
            self.registered_hotkey = keyboard.add_hotkey(hotkey_str, self.on_toggle_all)
            print(f"Hotkey '{hotkey_str}' registrado.")
        except Exception as e:
            messagebox.showerror("Erro de Hotkey", f"Não foi possível registrar o atalho '{hotkey_str}'.\nErro: {e}")

    def on_close(self, *args):
        self.monitoring_active.clear();
        if self.autopot: self.autopot.stop()
        if self.skillspam: self.skillspam.stop()
        if self.registered_hotkey:
            try: keyboard.remove_hotkey(self.registered_hotkey)
            except: pass
        self.destroy()

if __name__ == "__main__":
    is_admin = False
    try: is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except: pass
    if not is_admin:
        messagebox.showerror("Permissão Necessária", "Este programa precisa de privilégios de administrador.\nPor favor, execute como administrador.")
    else:
        app = App()
        app.mainloop()
