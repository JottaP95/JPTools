import time
import threading
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
# Adicionando pymem de volta para o AutoPot
import pymem

# --- CONFIGURAÇÕES E CONSTANTES ---
PROCESS_NAME = 'ragexe.exe'
# Endereços para o AutoPot. Serão lidos como endereços estáticos.
HP_ADDRESS = 0x014A175C
# Suposição comum: Max HP fica 4 bytes depois do HP atual.
MAX_HP_ADDRESS = 0x014A1760


# --- FUNÇÕES DE ENVIO DE COMANDO (JÁ FUNCIONAIS) ---

def SendMessage(hwnd, msg, wparam, lparam, flags=win32con.SMTO_ABORTIFHUNG, timeout=5000):
    return win32gui.SendMessageTimeout(hwnd, msg, wparam, lparam, flags, timeout)

def SendKey(hwnd, key: str) -> None:
    """ Envia um pressionamento de tecla completo para a janela. """
    try:
        char_code = ord(key.upper())
        vk_code = win32api.VkKeyScan(key.upper()) & 0xFF
        scan_code = win32api.MapVirtualKey(vk_code, 0)
        lparamdown = (scan_code << 16) | 1
        lparamup = (1 << 31) | (1 << 30) | (scan_code << 16) | 1
        
        SendMessage(hwnd, win32con.WM_KEYDOWN, vk_code, lparamdown)
        SendMessage(hwnd, win32con.WM_CHAR, char_code, lparamdown)
        time.sleep(0.02) # Pausa mínima
        SendMessage(hwnd, win32con.WM_KEYUP, vk_code, lparamup)
    except Exception as e:
        print(f"[ERRO] Falha ao enviar tecla: {e}")

def SendClick(hwnd, x=0, y=0) -> None:
    """ Envia um clique esquerdo para a janela. """
    SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, 0)
    time.sleep(0.02)
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

# --- CLASSE AUTOPOT COM NOVA LÓGICA E DIAGNÓSTICO ---
class AutoPot(threading.Thread):
    def __init__(self, pm, hwnd, use_key, threshold, hp_debug_var):
        super().__init__()
        self.pm = pm
        self.hwnd = hwnd
        self.use_key = use_key
        self.threshold = threshold
        self.running = threading.Event()
        self.daemon = True
        self.hp_debug_var = hp_debug_var # Variável da GUI para debug

    def run(self):
        self.running.set()
        print("Thread de AutoPot iniciada.")
        while self.running.is_set():
            try:
                # LÓGICA CORRIGIDA: Lendo de endereços estáticos, como no exemplo original.
                # Não somamos mais o endereço base.
                hp = self.pm.read_int(HP_ADDRESS)
                max_hp = self.pm.read_int(MAX_HP_ADDRESS)
                
                # DIAGNÓSTICO: Atualiza a label na interface para vermos os valores
                self.hp_debug_var.set(f"HP: {hp} / {max_hp}")

                if max_hp > 0:
                    hp_percent = (hp / max_hp)
                    if hp_percent < self.threshold:
                        print(f"\nHP baixo ({hp_percent:.0%}), usando poção na tecla '{self.use_key}'")
                        SendKey(self.hwnd, self.use_key)
                        time.sleep(0.3) # Cooldown para não potar demais
                time.sleep(0.1)
            except Exception as e:
                self.hp_debug_var.set("Erro na Leitura")
                print(f"\n[ERRO no AutoPot] Falha ao ler memória: {e}")
                time.sleep(1)

    def stop(self):
        self.running.clear()
        self.hp_debug_var.set("HP: N/A")
        print("\nThread de AutoPot parada.")

# --- CLASSES DA INTERFACE E SKILLSPAM (EXISTENTES) ---

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tipwindow or not self.text: return
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left', background="#ffffe0", relief='solid', borderwidth=1, font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
        self.tipwindow = None

class TriStateCheckbox(tk.Label):
    STATES = [" ", "✔", "–"]
    TOOLTIP_TEXTS = ["Desativado", "Skillspam + Clique", "Spam Somente Tecla"]

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
        keys_order = ['1','2','3','4','5','6','7','8','9','0','Q','W','E','R','T','Y','U','I','O','P','A','S','D','F','G','H','J','K','L','Z','X','C','V','B','N','M']
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
        print("Thread de SkillSpam iniciada.")
        while self.running.is_set():
            key_states = self.key_selector.get_key_states()
            for key, state in key_states.items():
                if state == 0: continue
                if keyboard.is_pressed(key):
                    if state == 1: self.send_key_and_click(key)
                    elif state == 2: self.send_key_only(key)
                    time.sleep(0.02)
            time.sleep(0.01)

    def send_key_and_click(self, key):
        SendKey(self.hwnd, key)
        SendClick(self.hwnd)

    def send_key_only(self, key):
        SendKey(self.hwnd, key)

    def stop(self):
        self.running.clear()
        print("Thread de SkillSpam parada.")


def play_toggle_sound(on=True):
    freq = 1000 if on else 600
    dur = 150
    winsound.Beep(freq, dur)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JPTools (SkillSpam + AutoPot)")
        self.geometry("450x450") # Aumentando um pouco a altura para a nova label
        self.resizable(False, False)

        self.pm = None
        self.hwnd = None
        self.skillspam = None
        self.autopot = None
        self.registered_hotkeys = []

        try:
            self.pm = pymem.Pymem(PROCESS_NAME)
            self.hwnd = get_hwnd_from_pid(self.pm.process_id)
            if not self.hwnd:
                messagebox.showerror("Erro", f"Processo '{PROCESS_NAME}' encontrado, mas sem janela visível.")
                self.destroy()
                return
        except pymem.exception.ProcessNotFound:
            messagebox.showerror("Erro de Conexão", f"Processo '{PROCESS_NAME}' não encontrado.")
            self.destroy()
            return
        except Exception as e:
            messagebox.showerror("Erro de Conexão", f"Falha ao conectar ao processo: {e}")
            self.destroy()
            return
            
        self.create_widgets()
        signal.signal(signal.SIGINT, self.signal_handler)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.register_hotkeys()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        ap_frame = ttk.LabelFrame(main_frame, text="Autopot")
        ap_frame.pack(fill='x', padx=5, pady=5)

        ap_key_frame = ttk.Frame(ap_frame)
        ap_key_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(ap_key_frame, text="Tecla da Poção:").pack(side="left")
        self.autopot_key_entry = ttk.Entry(ap_key_frame, width=5)
        self.autopot_key_entry.insert(0, "R")
        self.autopot_key_entry.pack(side="left", padx=5)
        ToolTip(self.autopot_key_entry, "Tecla que será pressionada para usar a poção.")

        ap_threshold_frame = ttk.Frame(ap_frame)
        ap_threshold_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(ap_threshold_frame, text="Usar se HP < (%):").pack(side="left")
        self.hp_threshold_entry = ttk.Entry(ap_threshold_frame, width=5)
        self.hp_threshold_entry.insert(0, "80")
        self.hp_threshold_entry.pack(side="left", padx=5)
        ToolTip(self.hp_threshold_entry, "Percentual de vida para ativar o autopot (ex: 80 para 80%).")

        # NOVO: Label de Diagnóstico na Interface
        debug_frame = ttk.Frame(ap_frame)
        debug_frame.pack(fill='x', padx=5, pady=5)
        self.hp_debug_var = tk.StringVar(value="HP: N/A")
        ttk.Label(debug_frame, text="Diagnóstico:", font=("Segoe UI", 8, "italic")).pack(side="left")
        ttk.Label(debug_frame, textvariable=self.hp_debug_var, font=("Courier", 9)).pack(side="left", padx=5)


        toggle_key_frame = ttk.Frame(main_frame)
        toggle_key_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(toggle_key_frame, text="Atalho Global (Ligar/Desligar Tudo):").pack(side="left")
        self.toggle_key_entry = ttk.Entry(toggle_key_frame, width=10)
        self.toggle_key_entry.insert(0, "F1")
        self.toggle_key_entry.pack(side="left", padx=5)
        self.toggle_key_entry.bind("<FocusOut>", lambda e: self.register_hotkeys())
        ToolTip(self.toggle_key_entry, "Tecla de atalho que liga ou desliga ambos, autopot e skillspam.")

        ss_frame = ttk.LabelFrame(main_frame, text="Skillspam (Clique para alterar: Vazio=Off, ✔=T+C, –=Tecla)")
        ss_frame.pack(fill='both', expand=True, padx=5, pady=10)
        self.key_selector = KeySelector(ss_frame)
        self.key_selector.pack()

    def register_hotkeys(self):
        for hk in self.registered_hotkeys:
            try: keyboard.remove_hotkey(hk)
            except Exception: pass
        self.registered_hotkeys.clear()

        def on_toggle_all():
            autopot_running = self.autopot and self.autopot.running.is_set()
            skillspam_running = self.skillspam and self.skillspam.running.is_set()
            
            if autopot_running or skillspam_running:
                if self.autopot: self.autopot.stop()
                if self.skillspam: self.skillspam.stop()
                play_toggle_sound(False)
                print("\nTudo desligado.")
            else:
                try:
                    pot_key = self.autopot_key_entry.get()
                    threshold = int(self.hp_threshold_entry.get()) / 100
                    if not pot_key or not (0 < threshold < 1):
                        messagebox.showerror("Erro", "Configurações do Autopot inválidas.")
                        return
                    
                    self.autopot = AutoPot(self.pm, self.hwnd, use_key=pot_key, threshold=threshold, hp_debug_var=self.hp_debug_var)
                    self.skillspam = SkillSpam(self.hwnd, self.key_selector)
                    self.autopot.start()
                    self.skillspam.start()
                    play_toggle_sound(True)
                    print("Tudo ligado.")
                except Exception as e:
                    messagebox.showerror("Erro ao Iniciar", f"Verifique as configurações. Detalhes: {e}")

        try:
            hotkey = self.toggle_key_entry.get()
            hk = keyboard.add_hotkey(hotkey, on_toggle_all)
            self.registered_hotkeys.append(hk)
        except Exception as e:
            print(f"[ERRO] Não foi possível registrar hotkey '{hotkey}': {e}")

    def on_close(self):
        print("[INFO] Fechando aplicação...")
        self.cleanup()
        self.destroy()

    def cleanup(self):
        if self.autopot: self.autopot.stop()
        if self.skillspam: self.skillspam.stop()

    def signal_handler(self, sig, frame):
        print("\n[INFO] Ctrl+C detectado! Encerrando...")
        self.cleanup()
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    app = App()
    app.mainloop()
