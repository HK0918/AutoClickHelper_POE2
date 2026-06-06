"""
Auto Click Helper - UI
========================
실행: python auto_click_helper_ui.py
poe2_tribute_clicker.py 와 같은 폴더에 위치해야 합니다.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import sys
import os
import json
import time
import queue

# poe2_tribute_clicker 모듈 임포트
if getattr(sys, 'frozen', False):
    _base_dir = sys._MEIPASS
else:
    _base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _base_dir)
os.chdir(_base_dir)

# ──────────────────────────────────────────────
#  색상 / 테마
# ──────────────────────────────────────────────
BG_DARK    = "#0d0d0f"
BG_PANEL   = "#141418"
BG_CARD    = "#1a1a22"
BORDER     = "#2a2a38"
ACCENT     = "#c8922a"        # 골드
ACCENT2    = "#e8b84b"
GREEN      = "#4caf74"
RED        = "#e05050"
BLUE       = "#5090d0"
TEXT_PRI   = "#e8e0d0"
TEXT_SEC   = "#888878"
TEXT_DIM   = "#555548"

FONT_TITLE = ("Georgia", 14, "bold")
FONT_HEAD  = ("Georgia", 10, "bold")
FONT_BTN   = ("Consolas", 9, "bold")
FONT_LOG   = ("Consolas", 8)
FONT_SMALL = ("Consolas", 8)

# ──────────────────────────────────────────────
#  로그 큐 (스레드 → UI)
# ──────────────────────────────────────────────
log_queue = queue.Queue()

class UILogger:
    """print를 가로채서 UI 로그창으로 전달"""
    def __init__(self, original, tag="info"):
        self.original = original
        self.tag = tag
    def write(self, msg):
        if msg and msg.strip():
            log_queue.put((self.tag, msg.rstrip()))
        if self.original and hasattr(self.original, 'write'):
            try:
                self.original.write(msg)
            except Exception:
                pass
    def flush(self):
        if self.original and hasattr(self.original, 'flush'):
            try:
                self.original.flush()
            except Exception:
                pass

# ──────────────────────────────────────────────
#  메인 앱
# ──────────────────────────────────────────────
class AutoClickHelperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Click Helper")
        self.root.configure(bg=BG_DARK)
        self.root.resizable(False, False)

        # 핫키 설정 (저장된 값 로드)
        self.hotkey_inv   = tk.StringVar(value="F1")
        self.hotkey_trib  = tk.StringVar(value="F2")
        if getattr(sys, 'frozen', False):
            _cfg_dir = os.path.dirname(sys.executable)
        else:
            _cfg_dir = os.path.dirname(os.path.abspath(__file__))
        self.hotkey_file = os.path.join(_cfg_dir, "hotkey_config.json")
        self._load_hotkeys()

        # 실행 상태
        self.running     = False
        self.module_ok   = False
        self.kbd_hook    = None

        self._build_ui()

        # stdout 리다이렉트 (UI 빌드 완료 후)
        sys.stdout = UILogger(sys.__stdout__, "info")
        self._init_module()
        self._poll_log()
        self._start_hotkey_listener()

    # ──────────────────────────────────────────
    #  UI 구성
    # ──────────────────────────────────────────
    def _build_ui(self):
        W = 520

        # ── 타이틀 바 ──
        title_frame = tk.Frame(self.root, bg=BG_DARK, pady=0)
        title_frame.pack(fill="x", padx=0, pady=0)

        tk.Canvas(title_frame, bg=BG_DARK, height=2, bd=0,
                  highlightthickness=0).pack(fill="x")

        header = tk.Frame(title_frame, bg=BG_DARK)
        header.pack(fill="x", padx=16, pady=(12,4))

        tk.Label(header, text="⚙  AUTO CLICK HELPER",
                 font=("Georgia", 15, "bold"),
                 fg=ACCENT2, bg=BG_DARK).pack(side="left")

        self.status_dot = tk.Label(header, text="●", font=("Consolas", 12),
                                   fg=TEXT_DIM, bg=BG_DARK)
        self.status_dot.pack(side="right", padx=(0,4))
        self.status_lbl = tk.Label(header, text="초기화 중...",
                                   font=FONT_SMALL, fg=TEXT_SEC, bg=BG_DARK)
        self.status_lbl.pack(side="right")

        self._sep()

        # ── 핫키 설정 ──
        self._section("HOTKEY 설정")
        hk_frame = tk.Frame(self.root, bg=BG_CARD, padx=12, pady=10)
        hk_frame.pack(fill="x", padx=12, pady=(0,8))

        self._hotkey_row(hk_frame, "인벤토리 클릭 (F1 역할)", self.hotkey_inv,  0)
        self._hotkey_row(hk_frame, "헌정품 클릭    (F2 역할)", self.hotkey_trib, 1)

        # ── 실행 버튼 ──
        self._section("실행")
        btn_outer = tk.Frame(self.root, bg=BG_DARK)
        btn_outer.pack(fill="x", padx=12, pady=(0,8))

        # 중단 안내
        stop_lbl = tk.Label(btn_outer, text="⚠  동작 중 우클릭으로 즉시 중단",
                            font=("Consolas", 8, "bold"),
                            fg="#e05050", bg=BG_DARK)
        stop_lbl.grid(row=0, column=0, columnspan=2, pady=(0, 6), sticky="w")

        # 버튼 그리드 (2열 × 4행, 완전 균등)
        btn_outer.columnconfigure(0, weight=1, uniform="col")
        btn_outer.columnconfigure(1, weight=1, uniform="col")

        buttons = [
            ("📦  인벤토리 Ctrl+클릭",      GREEN,     self._run_inventory,   0, 0),
            ("🏺  헌정품 자동 클릭",         ACCENT,    self._run_tribute,     0, 1),
            ("👁  인벤토리 미리보기 (Ctrl+F3)",   BLUE,      self._run_inv_preview, 1, 0),
            ("👁  헌정품 미리보기 (Ctrl+F4)",     BLUE,      self._run_trib_preview,1, 1),
            ("📐  인벤 캘리브레이션 (Ctrl+F5)",   "#6060a0", self._run_inv_calib,   2, 0),
            ("📐  헌정품 캘리브레이션 (Ctrl+F6)", "#6060a0", self._run_trib_calib,  2, 1),
            ("⚙  제외 칸 설정 (Ctrl+F7)",        "#505060", self._run_skip_cells,  3, 0),
            ("🎨  빈 칸 HSV 측정 (Ctrl+F8)",     "#505060", self._run_hsv,         3, 1),
        ]

        for text, color, cmd, row, col in buttons:
            b = self._btn(btn_outer, text, color, cmd)
            px_l = (0, 3) if col == 0 else (3, 0)
            b.grid(row=row, column=col, sticky="nsew",
                   padx=px_l, pady=3, ipady=4)

        # ── 로그 ──
        self._section("LOG")
        log_frame = tk.Frame(self.root, bg=BG_CARD, padx=1, pady=1)
        log_frame.pack(fill="both", expand=True, padx=12, pady=(0,4))

        self.log_box = scrolledtext.ScrolledText(
            log_frame, height=18, width=62,
            bg="#0a0a0e", fg=TEXT_PRI,
            font=FONT_LOG, bd=0, relief="flat",
            insertbackground=ACCENT,
            selectbackground=ACCENT,
        )
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_config("info",  foreground=TEXT_PRI)
        self.log_box.tag_config("ok",    foreground=GREEN)
        self.log_box.tag_config("warn",  foreground=ACCENT2)
        self.log_box.tag_config("error", foreground=RED)
        self.log_box.tag_config("dim",   foreground=TEXT_DIM)

        # 로그 버튼
        log_btn_frame = tk.Frame(self.root, bg=BG_DARK)
        log_btn_frame.pack(fill="x", padx=12, pady=(0,12))
        self._btn(log_btn_frame, "로그 지우기", TEXT_DIM,
                  self._clear_log, small=True, flat=True).pack(side="right")

        self._log("Auto Click Helper 시작됨", "dim")

    def _sep(self):
        f = tk.Frame(self.root, bg=BORDER, height=1)
        f.pack(fill="x", padx=0, pady=4)

    def _section(self, title):
        f = tk.Frame(self.root, bg=BG_DARK)
        f.pack(fill="x", padx=12, pady=(6,4))
        tk.Label(f, text=title, font=("Consolas", 7, "bold"),
                 fg=ACCENT, bg=BG_DARK).pack(side="left")
        tk.Frame(f, bg=BORDER, height=1).pack(side="left", fill="x",
                                               expand=True, padx=(6,0), pady=6)

    def _btn(self, parent, text, color, cmd, small=False, flat=False):
        relief = "flat"
        bg = BG_CARD if flat else color
        fg = TEXT_SEC if flat else BG_DARK

        b = tk.Button(
            parent, text=text, command=cmd,
            font=("Consolas", 9, "bold"),
            bg=bg, fg=fg, activebackground=ACCENT2, activeforeground=BG_DARK,
            relief=relief, bd=0, padx=8, pady=6,
            cursor="hand2",
        )
        # hover
        def on_enter(e, b=b, c=color, flat=flat):
            b.config(bg=ACCENT2 if not flat else BORDER, fg=BG_DARK)
        def on_leave(e, b=b, c=color, flat=flat):
            b.config(bg=(BG_CARD if flat else c), fg=(TEXT_SEC if flat else BG_DARK))
        b.bind("<Enter>", on_enter)
        b.bind("<Leave>", on_leave)
        return b

    def _hotkey_row(self, parent, label, var, row):
        tk.Label(parent, text=label, font=FONT_SMALL,
                 fg=TEXT_SEC, bg=BG_CARD, width=28,
                 anchor="w").grid(row=row, column=0, padx=(0,8), pady=3, sticky="w")

        entry = tk.Entry(parent, textvariable=var, width=8,
                         font=FONT_BTN, bg=BG_DARK, fg=ACCENT2,
                         insertbackground=ACCENT, relief="flat",
                         justify="center")
        entry.grid(row=row, column=1, padx=(0,8), pady=3)

        def start_capture(e=None, v=var, ent=entry):
            ent.config(fg=GREEN)
            v.set("입력 대기...")
            self.root.bind("<KeyPress>", lambda ev, v=v, ent=ent: self._capture_key(ev, v, ent))

        btn = tk.Button(parent, text="키 입력 저장",
                        font=("Consolas", 8), bg=BORDER, fg=TEXT_PRI,
                        relief="flat", bd=0, padx=6, pady=2,
                        cursor="hand2", command=start_capture)
        btn.grid(row=row, column=2, pady=3)

        def on_e(e, b=btn): b.config(bg=ACCENT, fg=BG_DARK)
        def on_l(e, b=btn): b.config(bg=BORDER, fg=TEXT_PRI)
        btn.bind("<Enter>", on_e)
        btn.bind("<Leave>", on_l)

    def _capture_key(self, event, var, entry):
        """키 입력 캡처"""
        key = event.keysym.upper()
        # F키 또는 알파벳만 허용
        if key.startswith("F") and key[1:].isdigit():
            var.set(key)
        elif len(key) == 1 and key.isalpha():
            var.set(key)
        else:
            var.set(key[:4])
        entry.config(fg=ACCENT2)
        self.root.unbind("<KeyPress>")
        self._save_hotkeys()
        self._start_hotkey_listener()
        self._log(f"핫키 저장: {var.get()}", "ok")

    # ──────────────────────────────────────────
    #  핫키 저장/로드
    # ──────────────────────────────────────────
    def _save_hotkeys(self):
        cfg = {"inv": self.hotkey_inv.get(), "trib": self.hotkey_trib.get()}
        with open(self.hotkey_file, "w") as f:
            json.dump(cfg, f)

    def _load_hotkeys(self):
        if os.path.exists(self.hotkey_file):
            try:
                cfg = json.load(open(self.hotkey_file))
                self.hotkey_inv.set(cfg.get("inv", "F1"))
                self.hotkey_trib.set(cfg.get("trib", "F2"))
            except:
                pass

    # ──────────────────────────────────────────
    #  글로벌 핫키 리스너
    # ──────────────────────────────────────────
    def _start_hotkey_listener(self):
        import keyboard as kb
        try:
            kb.unhook_all()
        except:
            pass

        inv_key  = self.hotkey_inv.get().lower()
        trib_key = self.hotkey_trib.get().lower()

        try:
            kb.add_hotkey(inv_key,    lambda: self.root.after(0, self._run_inventory),   suppress=False)
            kb.add_hotkey(trib_key,   lambda: self.root.after(0, self._run_tribute),     suppress=False)
            kb.add_hotkey("ctrl+f3",  lambda: self.root.after(0, self._run_inv_preview), suppress=False)
            kb.add_hotkey("ctrl+f4",  lambda: self.root.after(0, self._run_trib_preview),suppress=False)
            kb.add_hotkey("ctrl+f5",  lambda: threading.Thread(target=self._run_inv_calib,   daemon=True).start(), suppress=False)
            kb.add_hotkey("ctrl+f6",  lambda: threading.Thread(target=self._run_trib_calib,  daemon=True).start(), suppress=False)
            kb.add_hotkey("ctrl+f7",  lambda: self.root.after(0, self._run_skip_cells),  suppress=False)
            kb.add_hotkey("ctrl+f8",  lambda: threading.Thread(target=self._run_hsv,     daemon=True).start(), suppress=False)
            self._log(f"핫키 등록: {inv_key.upper()}=인벤 / {trib_key.upper()}=헌정품", "ok")
        except Exception as e:
            self._log(f"핫키 등록 실패: {e}", "warn")

    # ──────────────────────────────────────────
    #  모듈 초기화
    # ──────────────────────────────────────────
    def _init_module(self):
        def _load():
            try:
                import poe2_tribute_clicker as m
                self.m = m
                m.load_inv_config()
                m.load_tribute_config()
                self.module_ok = True
                self._set_status("준비", GREEN)
                self._log("모듈 로드 완료", "ok")
            except Exception as e:
                self.module_ok = False
                self._set_status("모듈 오류", RED)
                self._log(f"모듈 로드 실패: {e}", "error")
        threading.Thread(target=_load, daemon=True).start()

    def _check_module(self):
        if not self.module_ok:
            self._log("⚠ 모듈이 로드되지 않았습니다. poe2_tribute_clicker.py 확인!", "error")
            return False
        return True

    # ──────────────────────────────────────────
    #  버튼 액션
    # ──────────────────────────────────────────
    TASK_TIMEOUT = 5  # 초

    def _run_in_thread(self, fn, label, timeout=None):
        if not self._check_module():
            return
        if self.running:
            self._log("이미 실행 중입니다.", "warn")
            return
        def _task():
            self.running = True
            self._set_status(f"실행 중: {label}", ACCENT)
            # 타임아웃 타이머
            def _timeout():
                if self.running:
                    self.running = False
                    self._set_status("준비", GREEN)
                    self._log(f"⚠ [{label}] 타임아웃 ({t}초) → 초기화", "warn")
            t = timeout if timeout is not None else self.TASK_TIMEOUT
            timer = threading.Timer(t, _timeout)
            timer.daemon = True
            timer.start()
            try:
                fn()
            except Exception as e:
                self._log(f"오류: {e}", "error")
            finally:
                timer.cancel()
                self.running = False
                self._set_status("준비", GREEN)
        threading.Thread(target=_task, daemon=True).start()

    def _run_inventory(self):
        self._run_in_thread(self.m.inventory_ctrl_click, "인벤토리 클릭")

    def _run_tribute(self):
        self._run_in_thread(self.m.auto_click, "헌정품 클릭")

    def _run_inv_preview(self):
        self._run_in_thread(self.m.preview_inventory, "인벤 미리보기")

    def _run_trib_preview(self):
        self._run_in_thread(self.m.preview_detection, "헌정품 미리보기")

    def _run_inv_calib(self):
        self._run_in_thread(self.m.calibrate_inventory, "인벤 캘리브레이션", timeout=60)

    def _run_trib_calib(self):
        self._run_in_thread(self.m.calibrate_tribute, "헌정품 캘리브레이션", timeout=60)

    def _run_skip_cells(self):
        """제외 칸 설정 GUI - UI에서 직접 구현"""
        if not self._check_module():
            return

        m = self.m
        ROWS, COLS = m.INV_ROWS, m.INV_COLS

        win = tk.Toplevel(self.root)
        win.title("소지품창 제외 칸 설정")
        win.configure(bg=BG_DARK)
        win.resizable(False, False)
        win.grab_set()

        tk.Label(win, text="체크된 칸은 클릭하지 않습니다.",
                 font=("Consolas", 9), fg=TEXT_SEC, bg=BG_DARK,
                 pady=8).grid(row=0, column=0, columnspan=COLS+1)

        for c in range(COLS):
            tk.Label(win, text=str(c), width=3, font=("Consolas", 7),
                     fg=TEXT_DIM, bg=BG_DARK).grid(row=1, column=c+1)

        vars_ = []
        for r in range(ROWS):
            row_vars = []
            tk.Label(win, text=f"행{r}", font=("Consolas", 7),
                     fg=TEXT_DIM, bg=BG_DARK, width=3).grid(row=r+2, column=0)
            for c in range(COLS):
                checked = (r, c) in m.INV_SKIP_CELLS
                var = tk.IntVar(value=1 if checked else 0)
                bg_c = "#5a1a1a" if checked else BG_CARD
                cb = tk.Checkbutton(win, variable=var, width=2,
                                    bg=bg_c, activebackground=ACCENT,
                                    selectcolor="#3a0a0a",
                                    relief="flat", bd=0)
                def _update_bg(cb=cb, var=var):
                    cb.config(bg="#5a1a1a" if var.get() else BG_CARD)
                var.trace_add("write", lambda *a, f=_update_bg: f())
                cb.grid(row=r+2, column=c+1, padx=1, pady=1)
                row_vars.append(var)
            vars_.append(row_vars)

        def on_save():
            result = set()
            for r in range(ROWS):
                for c in range(COLS):
                    if vars_[r][c].get() == 1:
                        result.add((r, c))
            m.INV_SKIP_CELLS = result
            m.save_inv_config()
            self._log(f"✓ 제외 칸 {len(result)}개 저장", "ok")
            win.destroy()

        def select_all():
            for r in range(ROWS):
                for c in range(COLS):
                    vars_[r][c].set(1)

        def clear_all():
            for r in range(ROWS):
                for c in range(COLS):
                    vars_[r][c].set(0)

        btn_f = tk.Frame(win, bg=BG_DARK)
        btn_f.grid(row=ROWS+2, column=0, columnspan=COLS+1, pady=8)
        tk.Button(btn_f, text="전체선택", command=select_all,
                  bg=BORDER, fg=TEXT_PRI, font=("Consolas",8),
                  relief="flat", padx=6).pack(side="left", padx=3)
        tk.Button(btn_f, text="전체해제", command=clear_all,
                  bg=BORDER, fg=TEXT_PRI, font=("Consolas",8),
                  relief="flat", padx=6).pack(side="left", padx=3)
        tk.Button(btn_f, text="저장", command=on_save,
                  bg=GREEN, fg=BG_DARK, font=("Consolas",8,"bold"),
                  relief="flat", padx=10).pack(side="left", padx=3)
        tk.Button(btn_f, text="취소", command=win.destroy,
                  bg=BORDER, fg=TEXT_PRI, font=("Consolas",8),
                  relief="flat", padx=6).pack(side="left", padx=3)

    def _run_hsv(self):
        self._run_in_thread(self.m.measure_empty_cell_hsv, "빈 칸 HSV 측정", timeout=120)

    # ──────────────────────────────────────────
    #  로그
    # ──────────────────────────────────────────
    def _log(self, msg, tag="info"):
        log_queue.put((tag, msg))

    def _clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

    def _poll_log(self):
        """큐에서 로그 메시지를 가져와 UI에 표시"""
        try:
            while True:
                tag, msg = log_queue.get_nowait()
                # 태그 자동 감지
                if "✓" in msg or "완료" in msg or "성공" in msg:
                    tag = "ok"
                elif "✗" in msg or "오류" in msg or "실패" in msg or "Error" in msg:
                    tag = "error"
                elif "⚠" in msg or "경고" in msg:
                    tag = "warn"

                ts = time.strftime("%H:%M:%S")
                self.log_box.config(state="normal")
                self.log_box.insert("end", f"[{ts}] {msg}\n", tag)
                self.log_box.see("end")
                self.log_box.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log)

    def _set_status(self, text, color):
        def _update():
            self.status_lbl.config(text=text, fg=color)
            self.status_dot.config(fg=color)
        self.root.after(0, _update)


# ──────────────────────────────────────────────
#  진입점
# ──────────────────────────────────────────────
def main():
    root = tk.Tk()
    root.configure(bg=BG_DARK)

    # 창 크기 고정
    root.geometry("540x780")
    root.minsize(540, 780)

    app = AutoClickHelperApp(root)

    def on_close():
        try:
            import keyboard as kb
            kb.unhook_all()
        except:
            pass
        sys.stdout = sys.__stdout__
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
