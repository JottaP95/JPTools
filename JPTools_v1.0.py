import time
import pymem
import win32gui
import win32api
import win32con
import win32process

PROCESS_NAME = 'ragexe.exe'
HP_ADDRESS = 21628764
MAX_HP_ADDRESS = 21628768
USE_KEY = 'R'
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
        print(f"[INFO] Tecla '{key}' enviada.")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar tecla: {e}")

def get_hwnd_from_process_name(process_name):
    hwnd_list = []

    def callback(hwnd, _):
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid != 0:
            try:
                handle = pymem.Pymem(process_name)
                if handle.process_id == pid:
                    hwnd_list.append(hwnd)
            except:
                pass

    win32gui.EnumWindows(callback, None)
    return hwnd_list[0] if hwnd_list else None

def main():
    print("[INFO] Conectando ao processo...")
    pm = pymem.Pymem(PROCESS_NAME)

    print("[INFO] Buscando janela...")
    hwnd = win32gui.FindWindow(None, None)
    while hwnd:
        if win32gui.IsWindowVisible(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == pm.process_id:
                break
        hwnd = win32gui.GetWindow(hwnd, win32con.GW_HWNDNEXT)

    if not hwnd:
        print("[ERRO] Janela do processo não encontrada.")
        return

    print("[INFO] Iniciando loop do autopot.")
    while True:
        try:
            hp = pm.read_int(HP_ADDRESS)
            max_hp = pm.read_int(MAX_HP_ADDRESS)

            if max_hp == 0:
                continue

            hp_percent = hp / max_hp

            print(f"[DEBUG] HP: {hp}/{max_hp} ({hp_percent:.2%})")

            if hp_percent < POT_THRESHOLD:
                SendKey(hwnd, USE_KEY)

            time.sleep(0.2)  # 200ms entre checagens
        except Exception as e:
            print(f"[ERRO] {e}")
            break

if __name__ == "__main__":
    main()