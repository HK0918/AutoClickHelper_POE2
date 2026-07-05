"""
POE2 자동화 툴 v7 - 해상도 독립적 설계
========================================
필요 라이브러리:
    pip install pyautogui opencv-python numpy Pillow keyboard pywin32

준비 파일 (스크립트와 같은 폴더):
    tribute_symbol.png      - 헌정품 아이템 문양
    inventory_title.png     - 소지품창 타이틀
    (tribute_topleft/bottomright.png 더 이상 불필요)

핫키:
    F1  : 인벤토리 Ctrl+클릭 (아이템만)
    F2  : 헌정품 자동 클릭
    F3  : 인벤토리 그리드 미리보기
    F4  : 헌정품 감지 미리보기
    F5  : 인벤토리 캘리브레이션 (비율값 저장)
    F7  : 제외 칸 설정 (GUI)
    F8  : 빈 칸 HSV 범위 측정
    F9  : 헌정품 캘리브레이션
    종료: Ctrl+C
"""

import cv2
import numpy as np
import pyautogui
import keyboard
import time
import sys
import os
import json
import threading
from PIL import ImageGrab

# ──────────────────────────────────────────────
#  PyInstaller 번들 경로 처리
# ──────────────────────────────────────────────
def _res(filename):
    """번들 리소스 파일 경로 (png 등 읽기 전용)"""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS  # exe 임시 압축 해제 폴더
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, filename)

def _cfg(filename):
    """config 파일 경로 (읽기/쓰기 - exe 옆에 저장)"""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)  # exe 실행 폴더
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, filename)

# ──────────────────────────────────────────────
#  헌정품 설정
# ──────────────────────────────────────────────

TEMPLATE_SYMBOL          = _res("tribute_symbol.png")
TEMPLATE_LOCK            = _res("tribute_lock.png")
MATCH_THRESHOLD_SYMBOL   = 0.62
YELLOW_HSV_LOWER         = np.array([10,  80, 60])
YELLOW_HSV_UPPER         = np.array([45, 255, 255])
NMS_DIST                 = 35
CLICK_DELAY              = 0.035
TRIBUTE_CLICK_DELAY      = 0.05   # 헌정품 클릭 간격 (씹힘 방지)
TRIBUTE_MOUSE_HOLD       = 0.015  # 마우스 down→up 사이 대기

# 헌정품 그리드 config
TRIBUTE_CONFIG_FILE      = "tribute_config.json"
TRIBUTE_GRID_X_RATIO     = 0.0
TRIBUTE_GRID_Y_RATIO     = 0.0
TRIBUTE_GRID_W_RATIO     = 0.0
TRIBUTE_GRID_H_RATIO     = 0.0

# ──────────────────────────────────────────────
#  인벤토리 설정
# ──────────────────────────────────────────────

TEMPLATE_INV_TITLE       = _res("inventory_title.png")
INV_CONFIG_FILE          = "inventory_config.json"
INV_MATCH_THRESHOLD      = 0.70
INV_COLS                 = 12
INV_ROWS                 = 5

# 비율값 - config에서 로드
INV_GRID_X_RATIO         = 0.0   # 격자 시작 x / 화면너비  (절대좌표 비율)
INV_GRID_Y_RATIO         = 0.0   # 격자 시작 y / 화면높이
INV_CELL_W_RATIO         = 0.0   # 셀 너비 / 화면너비
INV_CELL_H_RATIO         = 0.0   # 셀 높이 / 화면높이

# 타이틀 기준 오프셋 비율 (타이틀 매칭 성공 시 사용)
INV_USE_TITLE            = False  # True면 타이틀+오프셋, False면 절대좌표
INV_OFFSET_X_RATIO       = 0.0
INV_OFFSET_Y_RATIO       = 0.0

# 빈 칸 HSV 범위
INV_EMPTY_HSV_LOWER      = np.array([100, 30,  5])
INV_EMPTY_HSV_UPPER      = np.array([140, 120, 60])
INV_EMPTY_RATIO          = 0.5

INV_SKIP_CELLS           = set()

# ──────────────────────────────────────────────
#  화면 캡처
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
#  중단 체크 (우클릭 또는 F3)
# ──────────────────────────────────────────────

_abort_flag = False

def _check_abort():
    """우클릭 또는 F3이 감지되면 True 반환"""
    global _abort_flag
    if _abort_flag:
        _abort_flag = False
        return True
    try:
        import win32api, win32con
        if win32api.GetAsyncKeyState(win32con.VK_RBUTTON) & 0x8000:
            print("  ✗ 우클릭 감지 → 중단")
            return True
    except Exception:
        pass
    if keyboard.is_pressed('f3'):
        print("  ✗ 중단 신호 감지 (F3)")
        return True
    return False


def get_screen_size():
    s = ImageGrab.grab()
    return s.size  # (width, height)

def capture_screen(region=None):
    if region:
        shot = ImageGrab.grab(bbox=(region[0], region[1],
                                    region[0]+region[2], region[1]+region[3]))
    else:
        shot = ImageGrab.grab()
    return cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)

# ──────────────────────────────────────────────
#  Config 로드/저장
# ──────────────────────────────────────────────

def load_inv_config():
    global INV_GRID_X_RATIO, INV_GRID_Y_RATIO
    global INV_CELL_W_RATIO, INV_CELL_H_RATIO
    global INV_USE_TITLE, INV_OFFSET_X_RATIO, INV_OFFSET_Y_RATIO
    global INV_SKIP_CELLS
    global INV_EMPTY_HSV_LOWER, INV_EMPTY_HSV_UPPER, INV_EMPTY_RATIO

    if not os.path.exists(_cfg(INV_CONFIG_FILE)):
        print("  ⚠ config 없음 → Ctrl+F5로 캘리브레이션 먼저 실행하세요")
        return False
    try:
        with open(_cfg(INV_CONFIG_FILE), 'r', encoding='utf-8') as f:
            cfg = json.load(f)

        INV_GRID_X_RATIO   = cfg.get('grid_x_ratio',   0.0)
        INV_GRID_Y_RATIO   = cfg.get('grid_y_ratio',   0.0)
        INV_CELL_W_RATIO   = cfg.get('cell_w_ratio',   0.0)
        INV_CELL_H_RATIO   = cfg.get('cell_h_ratio',   0.0)
        INV_USE_TITLE      = cfg.get('use_title',       False)
        INV_OFFSET_X_RATIO = cfg.get('offset_x_ratio', 0.0)
        INV_OFFSET_Y_RATIO = cfg.get('offset_y_ratio', 0.0)
        INV_SKIP_CELLS     = set(tuple(c) for c in cfg.get('skip_cells', []))

        if 'empty_hsv_lower' in cfg:
            INV_EMPTY_HSV_LOWER = np.array(cfg['empty_hsv_lower'])
            INV_EMPTY_HSV_UPPER = np.array(cfg['empty_hsv_upper'])
            INV_EMPTY_RATIO     = cfg.get('empty_ratio', INV_EMPTY_RATIO)

        sw, sh = get_screen_size()
        cell_w_px = int(sw * INV_CELL_W_RATIO)
        cell_h_px = int(sh * INV_CELL_H_RATIO)
        mode = "타이틀+오프셋" if INV_USE_TITLE else "절대좌표"
        cell_w_px = int(sw * INV_CELL_W_RATIO)
        cell_h_px = int(sh * INV_CELL_H_RATIO)
        print(f"  ✓ config 로드: 셀크기={cell_w_px}x{cell_h_px}px [{sw}x{sh}] 모드={mode} 제외칸={len(INV_SKIP_CELLS)}개")
        return True
    except Exception as e:
        print(f"  ⚠ config 로드 실패: {e}")
        return False


def save_inv_config():
    cfg = {
        'grid_x_ratio':   INV_GRID_X_RATIO,
        'grid_y_ratio':   INV_GRID_Y_RATIO,
        'cell_w_ratio':   INV_CELL_W_RATIO,
        'cell_h_ratio':   INV_CELL_H_RATIO,
        'calibrated_v2':  True,   # 6% 여유 적용된 버전
        'use_title':      INV_USE_TITLE,
        'offset_x_ratio': INV_OFFSET_X_RATIO,
        'offset_y_ratio': INV_OFFSET_Y_RATIO,
        'skip_cells':     [list(c) for c in INV_SKIP_CELLS],
        'empty_hsv_lower': INV_EMPTY_HSV_LOWER.tolist(),
        'empty_hsv_upper': INV_EMPTY_HSV_UPPER.tolist(),
        'empty_ratio':    INV_EMPTY_RATIO,
    }
    with open(_cfg(INV_CONFIG_FILE), 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f"  ✓ config 저장: {INV_CONFIG_FILE}")

# ──────────────────────────────────────────────
#  인벤토리 격자 위치 계산
# ──────────────────────────────────────────────

def find_inventory_grid():
    """
    비율값으로 격자 시작좌표와 셀크기(픽셀) 반환.
    - INV_USE_TITLE=True : 타이틀 템플릿 위치 + 오프셋 비율
    - INV_USE_TITLE=False: 절대좌표 비율로 직접 계산
    반환: (gx1, gy1, cell_w, cell_h) 또는 None
    """
    if INV_CELL_W_RATIO == 0.0:
        print("  ✗ 캘리브레이션 필요 → Ctrl+F5를 눌러 캘리브레이션 하세요")
        return None

    sw, sh = get_screen_size()
    cell_w = int(sw * INV_CELL_W_RATIO)
    cell_h = int(sh * INV_CELL_H_RATIO)

    if INV_USE_TITLE:
        # 타이틀 템플릿으로 위치 탐색
        if not os.path.exists(TEMPLATE_INV_TITLE):
            print(f"  ✗ 파일 없음: {TEMPLATE_INV_TITLE}")
            return None
        screen = capture_screen()
        tmpl   = cv2.imread(TEMPLATE_INV_TITLE)
        if tmpl is None:
            return None
        res = cv2.matchTemplate(screen, tmpl, cv2.TM_CCOEFF_NORMED)
        _, val, _, loc = cv2.minMaxLoc(res)
        if val < INV_MATCH_THRESHOLD:
            print(f"  ✗ 소지품창 타이틀 탐색 실패 (신뢰도 {val:.2f}) → 절대좌표로 폴백")
            # 폴백: 절대좌표 비율 사용
            gx1 = int(sw * INV_GRID_X_RATIO)
            gy1 = int(sh * INV_GRID_Y_RATIO)
        else:
            gx1 = int(loc[0] + sw * INV_OFFSET_X_RATIO)
            gy1 = int(loc[1] + sh * INV_OFFSET_Y_RATIO)
            print(f"  ✓ 소지품창 발견: 타이틀={loc} 신뢰도={val:.2f}")
    else:
        # 절대좌표 비율로 직접 계산
        gx1 = int(sw * INV_GRID_X_RATIO)
        gy1 = int(sh * INV_GRID_Y_RATIO)

    print(f"  ✓ 격자 시작: ({gx1},{gy1}), 셀크기: {cell_w}x{cell_h}  [{sw}x{sh}]")
    return (gx1, gy1, cell_w, cell_h)

# ──────────────────────────────────────────────
#  F5: 캘리브레이션
# ──────────────────────────────────────────────

def calibrate_inventory():
    global INV_GRID_X_RATIO, INV_GRID_Y_RATIO
    global INV_CELL_W_RATIO, INV_CELL_H_RATIO
    global INV_USE_TITLE, INV_OFFSET_X_RATIO, INV_OFFSET_Y_RATIO

    print("\n[캘리브레이션] 소지품창 격자 위치를 측정합니다.")
    print("  ┌──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┐")
    print("  │★│  │  │  │  │  │  │  │  │  │  │  │ ← 1번: 좌상단 첫 칸 좌상단 모서리")
    print("  ├──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┤")
    print("  │  │  │  │  │  │  │  │  │  │  │  │  │")
    print("  ├──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┤")
    print("  │  │  │  │  │  │  │  │  │  │  │  │  │")
    print("  ├──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┤")
    print("  │  │  │  │  │  │  │  │  │  │  │  │  │")
    print("  ├──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┤")
    print("  │  │  │  │  │  │  │  │  │  │  │  │★│ ← 2번: 우하단 마지막 칸 우하단 모서리")
    print("  └──┴──┴──┴──┴──┴──┴──┴──┴──┴──┴──┴──┘")
    print()
    print("  ▶ 좌상단 첫 칸 좌상단 모서리에 마우스를 올리고 스페이스바를 누르세요...")
    keyboard.wait("space")
    x1, y1 = pyautogui.position()
    print(f"  ✓ 1번: ({x1}, {y1})")

    print("  ▶ 우하단 마지막 칸 우하단 모서리에 마우스를 올리고 스페이스바를 누르세요...")
    keyboard.wait("space")
    x2, y2 = pyautogui.position()
    print(f"  ✓ 2번: ({x2}, {y2})")

    sw, sh = get_screen_size()

    # 셀 크기 계산 (모서리→모서리 기준)
    cell_w_px = (x2 - x1) / 12.0   # 전체 너비 / 12칸
    cell_h_px = (y2 - y1) / 5.0    # 전체 높이 / 5행
    gx1_px    = float(x1)           # 모서리가 바로 격자 시작점
    gy1_px    = float(y1)

    INV_CELL_W_RATIO = cell_w_px / sw
    INV_CELL_H_RATIO = cell_h_px / sh

    # 절대좌표 비율 (항상 저장) - 약간의 여유 포함
    INV_GRID_X_RATIO = gx1_px / sw
    INV_GRID_Y_RATIO = gy1_px / sh

    print(f"  셀크기: {cell_w_px}x{cell_h_px}px → 비율: {INV_CELL_W_RATIO:.6f}x{INV_CELL_H_RATIO:.6f}")
    print(f"  격자시작: ({gx1_px},{gy1_px}) → 비율: {INV_GRID_X_RATIO:.6f}x{INV_GRID_Y_RATIO:.6f}")

    # 타이틀 매칭 시도 (성공하면 더 정확한 오프셋 방식 사용)
    screen = capture_screen()
    tmpl   = cv2.imread(TEMPLATE_INV_TITLE)
    if tmpl is not None:
        res = cv2.matchTemplate(screen, tmpl, cv2.TM_CCOEFF_NORMED)
        _, val, _, loc = cv2.minMaxLoc(res)
        if val >= 0.6:
            INV_USE_TITLE      = True
            INV_OFFSET_X_RATIO = (gx1_px - loc[0]) / sw
            INV_OFFSET_Y_RATIO = (gy1_px - loc[1]) / sh
            print(f"  ✓ 타이틀 매칭 성공: {loc}, 신뢰도={val:.2f} → 타이틀+오프셋 모드")
            print(f"  ✓ 오프셋 비율: {INV_OFFSET_X_RATIO:.6f} / {INV_OFFSET_Y_RATIO:.6f}")
        else:
            INV_USE_TITLE = False
            print(f"  ⚠ 타이틀 매칭 실패 (신뢰도 {val:.2f}) → 절대좌표 모드")
    else:
        INV_USE_TITLE = False
        print("  ⚠ inventory_title.png 없음 → 절대좌표 모드")

    save_inv_config()
    print("  ✓ 캘리브레이션 완료! Ctrl+F3으로 미리보기 확인하세요.")

# ──────────────────────────────────────────────
#  F8: 빈 칸 HSV 범위 측정
# ──────────────────────────────────────────────

def measure_empty_cell_hsv():
    global INV_EMPTY_HSV_LOWER, INV_EMPTY_HSV_UPPER, INV_EMPTY_RATIO

    print("\n[빈 칸 HSV 측정]")
    print("  마우스를 빈 칸 위에 올리고 스페이스바로 측정 (여러 칸 가능)")
    print("  F6: 측정 완료 및 저장")

    samples_h, samples_s, samples_v = [], [], []
    done = [False]
    sw, sh = get_screen_size()

    def on_space():
        x, y = pyautogui.position()
        frame = capture_screen()
        cell_w = max(1, int(sw * INV_CELL_W_RATIO))
        cell_h = max(1, int(sh * INV_CELL_H_RATIO))
        x1 = max(0, x - cell_w//2 + 3)
        y1 = max(0, y - cell_h//2 + 3)
        x2 = min(frame.shape[1], x1 + cell_w - 6)
        y2 = min(frame.shape[0], y1 + cell_h - 6)
        patch = frame[y1:y2, x1:x2]
        hsv   = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        samples_h.extend(hsv[:,:,0].flatten().tolist())
        samples_s.extend(hsv[:,:,1].flatten().tolist())
        samples_v.extend(hsv[:,:,2].flatten().tolist())
        n = len(samples_h) // max(1, (cell_w-6)*(cell_h-6))
        print(f"  ✓ ({x},{y}) 측정됨 (총 {n+1}칸)")

    def on_f6():
        done[0] = True

    keyboard.add_hotkey('space', on_space)
    keyboard.add_hotkey('f6', on_f6)
    while not done[0]:
        time.sleep(0.1)
    keyboard.remove_hotkey('space')
    keyboard.remove_hotkey('f6')

    if not samples_h:
        print("  ✗ 측정된 데이터 없음")
        return

    h_arr = np.array(samples_h)
    s_arr = np.array(samples_s)
    v_arr = np.array(samples_v)

    INV_EMPTY_HSV_LOWER = np.array([
        max(0,   int(h_arr.mean() - h_arr.std() * 2)),
        max(0,   int(s_arr.mean() - s_arr.std() * 2)),
        max(0,   int(v_arr.mean() - v_arr.std() * 2)),
    ])
    INV_EMPTY_HSV_UPPER = np.array([
        min(180, int(h_arr.mean() + h_arr.std() * 2)),
        min(255, int(s_arr.mean() + s_arr.std() * 2)),
        min(255, int(v_arr.mean() + v_arr.std() * 2)),
    ])

    print(f"  ✓ 빈 칸 HSV → Lower: {INV_EMPTY_HSV_LOWER}  Upper: {INV_EMPTY_HSV_UPPER}")
    save_inv_config()
    print("  ✓ 저장 완료!")

# ──────────────────────────────────────────────
#  빈 칸 판단
# ──────────────────────────────────────────────

def is_empty_cell(patch_bgr):
    hsv   = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2HSV)
    mask  = cv2.inRange(hsv, INV_EMPTY_HSV_LOWER, INV_EMPTY_HSV_UPPER)
    ratio = cv2.countNonZero(mask) / max(1, patch_bgr.shape[0] * patch_bgr.shape[1])
    return ratio >= INV_EMPTY_RATIO

# ──────────────────────────────────────────────
#  F7: 제외 칸 설정 GUI
# ──────────────────────────────────────────────

def edit_skip_cells():
    global INV_SKIP_CELLS
    import tkinter as tk

    print("\n[제외 칸 설정] GUI 창을 열었습니다...")
    root = tk.Tk()
    root.title("소지품창 제외 칸 설정")
    root.resizable(False, False)

    tk.Label(root, text="체크된 칸은 클릭하지 않습니다.",
             font=("맑은 고딕", 10), pady=6).grid(row=0, column=0, columnspan=INV_COLS+1)
    for c in range(INV_COLS):
        tk.Label(root, text=str(c), width=4, font=("맑은 고딕", 8),
                 fg="gray").grid(row=1, column=c+1)

    vars_ = []
    for r in range(INV_ROWS):
        row_vars = []
        tk.Label(root, text=f"행{r}", font=("맑은 고딕", 8),
                 fg="gray", width=3).grid(row=r+2, column=0)
        for c in range(INV_COLS):
            # BooleanVar 대신 IntVar 사용 (스레드 안전성 향상)
            var = tk.IntVar(value=1 if (r, c) in INV_SKIP_CELLS else 0)
            cb  = tk.Checkbutton(root, variable=var, width=2,
                                 bg="#ffcccc" if (r,c) in INV_SKIP_CELLS else "white")
            var.trace_add("write", lambda *a, cb=cb, var=var: cb.config(
                bg="#ffcccc" if var.get() else "white"))
            cb.grid(row=r+2, column=c+1, padx=1, pady=1)
            row_vars.append(var)
        vars_.append(row_vars)

    btn_frame = tk.Frame(root)
    btn_frame.grid(row=INV_ROWS+2, column=0, columnspan=INV_COLS+1, pady=6)

    def on_save():
        global INV_SKIP_CELLS
        result = set()
        for r in range(INV_ROWS):
            for c in range(INV_COLS):
                if vars_[r][c].get() == 1:
                    result.add((r, c))
        INV_SKIP_CELLS = result
        save_inv_config()
        print(f"  ✓ 제외 칸 {len(result)}개 저장")
        root.destroy()

    def select_all():
        for r in range(INV_ROWS):
            for c in range(INV_COLS):
                vars_[r][c].set(1)

    def clear_all():
        for r in range(INV_ROWS):
            for c in range(INV_COLS):
                vars_[r][c].set(0)

    tk.Button(btn_frame, text="전체 선택", command=select_all,    width=8).pack(side="left", padx=4)
    tk.Button(btn_frame, text="전체 해제", command=clear_all,     width=8).pack(side="left", padx=4)
    tk.Button(btn_frame, text="저장",      command=on_save,       width=8,
              bg="#4CAF50", fg="white").pack(side="left", padx=4)
    tk.Button(btn_frame, text="취소",      command=root.destroy,  width=8).pack(side="left", padx=4)

    root.mainloop()

# ──────────────────────────────────────────────
#  F3: 인벤토리 미리보기
# ──────────────────────────────────────────────

def preview_inventory():
    print("\n[인벤 미리보기] 소지품창 탐색 중...")
    result = find_inventory_grid()
    if result is None:
        return
    gx1, gy1, cell_w, cell_h = result

    frame = capture_screen()
    fh, fw = frame.shape[:2]

    for r in range(INV_ROWS):
        for c in range(INV_COLS):
            x1 = gx1 + c * cell_w
            y1 = gy1 + r * cell_h
            x2 = min(x1 + cell_w, fw)
            y2 = min(y1 + cell_h, fh)
            if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
                continue
            patch = frame[y1+3:y2-3, x1+3:x2-3]
            empty = is_empty_cell(patch) if patch.size > 0 else True
            skip  = (r, c) in INV_SKIP_CELLS

            if skip:
                color = (80, 80, 80)
            elif empty:
                color = (200, 100, 50)   # 파란색 = 빈 칸
            else:
                color = (0, 255, 0)      # 초록 = 아이템
            cv2.rectangle(frame, (x1,y1), (x2,y2), color, 1)
            if not empty and not skip:
                cv2.circle(frame, ((x1+x2)//2, (y1+y2)//2), 3, (0,0,255), -1)

    cv2.namedWindow("인벤토리 미리보기 (아무 키나 닫힘)", cv2.WINDOW_NORMAL)
    cv2.imshow("인벤토리 미리보기 (아무 키나 닫힘)", frame)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    print("  초록=아이템, 파랑=빈칸, 회색=제외칸")

# ──────────────────────────────────────────────
#  F1: 인벤토리 Ctrl+클릭
# ──────────────────────────────────────────────

def inventory_ctrl_click():
    print("\n[인벤토리 Ctrl+클릭] 소지품창 탐색 중...")
    result = find_inventory_grid()
    if result is None:
        print("  ✗ 소지품창을 찾을 수 없습니다.")
        return
    gx1, gy1, cell_w, cell_h = result

    print("  0.1초 후 시작...")
    print(f"  제외 칸: {sorted(INV_SKIP_CELLS)}")
    time.sleep(0.1)

    frame = capture_screen()
    fh, fw = frame.shape[:2]
    print(f"  화면크기: {fw}x{fh}, 격자범위: ({gx1},{gy1})~({gx1+cell_w*INV_COLS},{gy1+cell_h*INV_ROWS})")

    click_cells = []
    oob = 0
    for r in range(INV_ROWS):
        for c in range(INV_COLS):
            if (r, c) in INV_SKIP_CELLS:
                continue
            x1 = gx1 + c * cell_w + 3
            y1 = gy1 + r * cell_h + 3
            x2 = x1 + cell_w - 6
            y2 = y1 + cell_h - 6
            if x1 < 0 or y1 < 0 or x2 > fw or y2 > fh:
                oob += 1
                continue
            patch = frame[y1:y2, x1:x2]
            if patch.size > 0 and not is_empty_cell(patch):
                click_cells.append((r, c))

    if oob:
        print(f"  ⚠ 화면 범위 밖 셀: {oob}개")
    print(f"  아이템 감지: {len(click_cells)}개 (빈 칸 스킵)")

    count = 0
    prev_pause = pyautogui.PAUSE
    pyautogui.PAUSE = 0
    try:
        for r, c in click_cells:
            if _check_abort():
                return
            # 클릭 전 다시 확인 (이미 이동된 칸 스킵)
            cur_frame = capture_screen()
            x1 = gx1 + c * cell_w + 3
            y1 = gy1 + r * cell_h + 3
            x2 = x1 + cell_w - 6
            y2 = y1 + cell_h - 6
            patch = cur_frame[y1:y2, x1:x2]
            if patch.size > 0 and is_empty_cell(patch):
                continue  # 이미 비워진 칸 스킵

            cx = gx1 + c * cell_w + cell_w // 2
            cy = gy1 + r * cell_h + cell_h // 2
            pyautogui.keyDown('ctrl')
            pyautogui.click(cx, cy)
            pyautogui.keyUp('ctrl')
            count += 1
            time.sleep(CLICK_DELAY)
    finally:
        pyautogui.PAUSE = prev_pause

    print(f"  완료! ({count}개 클릭)")

# ──────────────────────────────────────────────
#  Ctrl+Shift+클릭 (탭 이동용)
# ──────────────────────────────────────────────

def inventory_shift_click():
    """
    인벤토리 클릭과 동일하지만 Ctrl+Shift+클릭으로 수행.
    보관함 탭 간 아이템 이동 등에 사용.
    """
    print("\n[Ctrl+Shift+클릭] 소지품창 탐색 중...")
    result = find_inventory_grid()
    if result is None:
        print("  ✗ 소지품창을 찾을 수 없습니다.")
        return
    gx1, gy1, cell_w, cell_h = result

    print("  0.1초 후 시작...")
    time.sleep(0.1)

    frame = capture_screen()
    fh, fw = frame.shape[:2]

    click_cells = []
    oob = 0
    for r in range(INV_ROWS):
        for c in range(INV_COLS):
            if (r, c) in INV_SKIP_CELLS:
                continue
            x1 = gx1 + c * cell_w + 3
            y1 = gy1 + r * cell_h + 3
            x2 = x1 + cell_w - 6
            y2 = y1 + cell_h - 6
            if x1 < 0 or y1 < 0 or x2 > fw or y2 > fh:
                oob += 1
                continue
            patch = frame[y1:y2, x1:x2]
            if patch.size > 0 and not is_empty_cell(patch):
                click_cells.append((r, c))

    if oob:
        print(f"  ⚠ 화면 범위 밖 셀: {oob}개")
    print(f"  아이템 감지: {len(click_cells)}개 (빈 칸 스킵)")

    count = 0
    prev_pause = pyautogui.PAUSE
    pyautogui.PAUSE = 0
    try:
        for r, c in click_cells:
            if _check_abort():
                return
            cur_frame = capture_screen()
            x1 = gx1 + c * cell_w + 3
            y1 = gy1 + r * cell_h + 3
            x2 = x1 + cell_w - 6
            y2 = y1 + cell_h - 6
            patch = cur_frame[y1:y2, x1:x2]
            if patch.size > 0 and is_empty_cell(patch):
                continue

            cx = gx1 + c * cell_w + cell_w // 2
            cy = gy1 + r * cell_h + cell_h // 2
            pyautogui.keyDown('ctrl')
            pyautogui.keyDown('shift')
            pyautogui.click(cx, cy)
            pyautogui.keyUp('shift')
            pyautogui.keyUp('ctrl')
            count += 1
            time.sleep(CLICK_DELAY)
    finally:
        pyautogui.PAUSE = prev_pause

    print(f"  완료! ({count}개 클릭)")


# ──────────────────────────────────────────────
#  헌정품 관련 함수
# ──────────────────────────────────────────────


# ──────────────────────────────────────────────
#  헌정품 Config 로드/저장
# ──────────────────────────────────────────────

def load_tribute_config():
    global TRIBUTE_GRID_X_RATIO, TRIBUTE_GRID_Y_RATIO
    global TRIBUTE_GRID_W_RATIO, TRIBUTE_GRID_H_RATIO
    if not os.path.exists(_cfg(TRIBUTE_CONFIG_FILE)):
        print("  ⚠ 헌정품 config 없음 → Ctrl+F6으로 캘리브레이션 먼저 실행하세요")
        return False
    try:
        with open(_cfg(TRIBUTE_CONFIG_FILE), 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        TRIBUTE_GRID_X_RATIO = cfg.get('grid_x_ratio', 0.0)
        TRIBUTE_GRID_Y_RATIO = cfg.get('grid_y_ratio', 0.0)
        TRIBUTE_GRID_W_RATIO = cfg.get('grid_w_ratio', 0.0)
        TRIBUTE_GRID_H_RATIO = cfg.get('grid_h_ratio', 0.0)
        sw, sh = get_screen_size()
        print(f"  ✓ 헌정품 config 로드: 그리드 ({int(sw*TRIBUTE_GRID_X_RATIO)},{int(sh*TRIBUTE_GRID_Y_RATIO)}) "
              f"{int(sw*TRIBUTE_GRID_W_RATIO)}x{int(sh*TRIBUTE_GRID_H_RATIO)}px [{sw}x{sh}]")
        return True
    except Exception as e:
        print(f"  ⚠ 헌정품 config 로드 실패: {e}")
        return False


def save_tribute_config():
    cfg = {
        'grid_x_ratio': TRIBUTE_GRID_X_RATIO,
        'grid_y_ratio': TRIBUTE_GRID_Y_RATIO,
        'grid_w_ratio': TRIBUTE_GRID_W_RATIO,
        'grid_h_ratio': TRIBUTE_GRID_H_RATIO,
    }
    with open(_cfg(TRIBUTE_CONFIG_FILE), 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f"  ✓ 헌정품 config 저장: {TRIBUTE_CONFIG_FILE}")


def get_tribute_grid_region():
    """비율값으로 헌정품 그리드 영역 (left, top, w, h) 반환"""
    if TRIBUTE_GRID_W_RATIO == 0.0:
        print("  ✗ 헌정품 캘리브레이션 필요 → Ctrl+F6을 눌러주세요")
        return None
    sw, sh = get_screen_size()
    left = int(sw * TRIBUTE_GRID_X_RATIO)
    top  = int(sh * TRIBUTE_GRID_Y_RATIO)
    w    = int(sw * TRIBUTE_GRID_W_RATIO)
    h    = int(sh * TRIBUTE_GRID_H_RATIO)
    print(f"  ✓ 헌정품 그리드: ({left},{top}) {w}x{h}px  [{sw}x{sh}]")
    return (left, top, w, h)


# ──────────────────────────────────────────────
#  F9: 헌정품 캘리브레이션
# ──────────────────────────────────────────────

def calibrate_tribute():
    global TRIBUTE_GRID_X_RATIO, TRIBUTE_GRID_Y_RATIO
    global TRIBUTE_GRID_W_RATIO, TRIBUTE_GRID_H_RATIO

    print("\n[헌정품 캘리브레이션] 12x10 그리드 영역을 지정합니다.")
    print("  헌정품 창이 열린 상태에서:")
    print()
    print("  ┌──┬──┬── ... ──┬──┐")
    print("  │★ ← 1번: 그리드 맨 좌상단 모서리 (첫 칸 좌상단)")
    print("  ├──┼──┼── ... ──┼──┤")
    print("  │  │  │         │  │")
    print("  ├──┼──┼── ... ──┼──┤")
    print("  │                ★ │ ← 2번: 그리드 맨 우하단 모서리 (마지막 칸 우하단)")
    print("  └──┴──┴── ... ──┴──┘")
    print()
    print("  ※ 아이템이 있는 칸만이 아니라 전체 12x10 그리드 영역을 지정하세요!")
    print()
    print("  ▶ 그리드 좌상단 모서리에 마우스를 올리고 스페이스바를 누르세요...")
    keyboard.wait("space")
    x1, y1 = pyautogui.position()
    print(f"  ✓ 좌상단: ({x1}, {y1})")

    print("  ▶ 그리드 우하단 (마지막 칸 우하단)에 마우스를 올리고 스페이스바를 누르세요...")
    keyboard.wait("space")
    x2, y2 = pyautogui.position()
    print(f"  ✓ 우하단: ({x2}, {y2})")

    sw, sh = get_screen_size()
    TRIBUTE_GRID_X_RATIO = x1 / sw
    TRIBUTE_GRID_Y_RATIO = y1 / sh
    TRIBUTE_GRID_W_RATIO = (x2 - x1) / sw
    TRIBUTE_GRID_H_RATIO = (y2 - y1) / sh

    print(f"  그리드: ({x1},{y1})~({x2},{y2}), 크기: {x2-x1}x{y2-y1}px")
    print(f"  비율: x={TRIBUTE_GRID_X_RATIO:.6f} y={TRIBUTE_GRID_Y_RATIO:.6f} "
          f"w={TRIBUTE_GRID_W_RATIO:.6f} h={TRIBUTE_GRID_H_RATIO:.6f}")
    save_tribute_config()
    print("  ✓ 헌정품 캘리브레이션 완료! F4로 미리보기 확인하세요.")

def find_template_on_screen(screen, path, label, threshold):
    tmpl = cv2.imread(path)
    if tmpl is None:
        return None
    th, tw = tmpl.shape[:2]
    res = cv2.matchTemplate(screen, tmpl, cv2.TM_CCOEFF_NORMED)
    _, val, _, loc = cv2.minMaxLoc(res)
    if val < threshold:
        return None
    return (loc[0], loc[1], tw, th)

def find_grid_region(screen):
    tl = find_template_on_screen(screen, TEMPLATE_TL, "좌상단", MATCH_THRESHOLD_WINDOW)
    br = find_template_on_screen(screen, TEMPLATE_BR, "우하단", MATCH_THRESHOLD_WINDOW)
    if tl is None or br is None:
        return None
    left, top     = tl[0], tl[1]
    right, bottom = br[0]+br[2], br[1]+br[3]
    w, h = right-left, bottom-top
    if w <= 0 or h <= 0:
        return None
    return (left, top, w, h)

def nms_points(points, scores, min_dist):
    if not points:
        return []
    paired = sorted(zip(scores, points), reverse=True)
    kept = []
    for score, p in paired:
        if not any(abs(p[0]-k[0]) < min_dist and abs(p[1]-k[1]) < min_dist for k in kept):
            kept.append(p)
    return kept

def find_items_by_symbol(grid_img, grid_offset=(0, 0)):
    if not os.path.exists(TEMPLATE_SYMBOL):
        return []
    symbol = cv2.imread(TEMPLATE_SYMBOL)
    if symbol is None:
        return []
    sh, sw = symbol.shape[:2]
    ox, oy = grid_offset

    # 멀티스케일 매칭 - 해상도/UI 크기가 달라도 동작
    best_res   = None
    best_score = 0
    best_sw, best_sh = sw, sh

    for scale in [0.7, 0.8, 0.9, 1.0, 1.1, 1.2]:
        nw = max(1, int(sw * scale))
        nh = max(1, int(sh * scale))
        if nw > grid_img.shape[1] or nh > grid_img.shape[0]:
            continue
        sym_r = cv2.resize(symbol, (nw, nh))
        res   = cv2.matchTemplate(grid_img, sym_r, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        if max_val > best_score:
            best_score = max_val
            best_res   = res
            best_sw, best_sh = nw, nh

    if best_res is None or best_score < MATCH_THRESHOLD_SYMBOL:
        print(f"  [문양] 0개 감지 (최고 신뢰도: {best_score:.2f})")
        return []

    locs     = np.where(best_res >= MATCH_THRESHOLD_SYMBOL)
    points   = list(zip(locs[1].tolist(), locs[0].tolist()))
    scores   = [best_res[y, x] for x, y in points]
    filtered = nms_points(points, scores, NMS_DIST)

    results = []
    for (lx, ly) in filtered:
        results.append((ox+lx+best_sw//2, oy+ly+best_sh//2,
                        best_sw, best_sh, lx, ly, 'symbol'))
    results.sort(key=lambda r: (r[5], r[4]))
    print(f"  [문양] {len(results)}개 감지 (신뢰도 {best_score:.2f})")
    return results

def find_items_by_border(grid_img, grid_offset=(0, 0)):
    h_img, w_img = grid_img.shape[:2]
    hsv  = cv2.cvtColor(grid_img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, YELLOW_HSV_LOWER, YELLOW_HSV_UPPER)

    # 노이즈 제거 후 테두리 연결
    k_open  = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (4, 4))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k_open,  iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k_close, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    results = []
    ox, oy  = grid_offset

    # 헌정품 그리드 셀 크기 추정 (12x10 기준)
    est_cell_w = w_img / 12.0
    est_cell_h = h_img / 10.0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 300:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 20 or h < 20:
            continue

        # 내부 노란 비율 체크 (테두리는 내부가 비어있음)
        margin = max(5, min(w, h) // 6)
        inner  = mask[y+margin:y+h-margin, x+margin:x+w-margin]
        inner_ratio = cv2.countNonZero(inner) / max(1, inner.size) if inner.size > 0 else 1.0

        # 헌정품 박스: 내부 노란 비율 낮음 (테두리만 있음)
        if inner_ratio > 0.3:
            continue

        # 일반 아이템 칸 테두리와 구분: 셀 크기의 0.8~4배 범위만 허용
        if w < est_cell_w * 0.5 or w > est_cell_w * 5:
            continue
        if h < est_cell_h * 0.5 or h > est_cell_h * 5:
            continue

        results.append((ox+x+w//2, oy+y+h//2, w, h, x, y, 'border'))

    results.sort(key=lambda r: (r[5]//10, r[4]))
    print(f"  [테두리] {len(results)}개 감지")
    return results

def find_items(grid_img, grid_offset=(0, 0)):
    sym = find_items_by_symbol(grid_img, grid_offset)
    print(f"  → 문양 방식 사용 ({len(sym)}개)")
    return sym

def click_lock_button(screen):
    """
    헌정품 그리드 캘리브레이션 기준으로 자물쇠 버튼 클릭.
    자물쇠는 그리드 우상단 모서리에서 위로 약 0.7셀 위치.
    """
    region = get_tribute_grid_region()
    if region is None:
        return False

    left, top, w, h = region
    sw, sh = get_screen_size()
    cell_w = w / 12.0
    cell_h = h / 10.0

    # 자물쇠 위치: 그리드 우상단 모서리 기준, 좌측 1칸, 위로 0.7셀
    cx = int(left + w - cell_w * 1.5)   # 우측 끝에서 1.5칸 안쪽 (한 칸 왼쪽)
    cy = int(top  - cell_h * 0.7)        # 그리드 위로 0.7셀
    print(f"  ✓ 자물쇠 클릭: ({cx},{cy})")
    pyautogui.click(cx, cy)
    return True

def preview_detection():
    print("\n[헌정품 미리보기] 탐색 중...")
    region = get_tribute_grid_region()
    if region is None:
        return
    grid_img = capture_screen(region)
    items    = find_items(grid_img, grid_offset=(region[0], region[1]))
    if not items:
        print("  ✗ 아이템 없음")
    else:
        print(f"  ✓ {len(items)}개 감지")

    preview = grid_img.copy()
    cv2.rectangle(preview,(0,0),(preview.shape[1]-1,preview.shape[0]-1),(0,165,255),2)
    for i,(sx,sy,w,h,lx,ly,method) in enumerate(items):
        color = (0,255,0) if method=='symbol' else (0,200,255)
        cv2.rectangle(preview,(lx,ly),(lx+w,ly+h),color,2)
        cv2.circle(preview,(lx+w//2,ly+h//2),4,(0,0,255),-1)
        cv2.putText(preview,str(i+1),(lx+3,ly+16),cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,255,255),1)

    hsv  = cv2.cvtColor(grid_img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, YELLOW_HSV_LOWER, YELLOW_HSV_UPPER)
    cv2.namedWindow("헌정품 미리보기 (아무 키나 닫힘)", cv2.WINDOW_NORMAL)
    cv2.imshow("헌정품 미리보기 (아무 키나 닫힘)", preview)
    cv2.namedWindow("노란색 마스크", cv2.WINDOW_NORMAL)
    cv2.imshow("노란색 마스크", mask)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

def auto_click():
    print("\n[헌정품 자동 클릭] 탐색 중...")
    region = get_tribute_grid_region()
    if region is None:
        return
    grid_img = capture_screen(region)
    items    = find_items(grid_img, grid_offset=(region[0], region[1]))
    if not items:
        print("  ✗ 아이템 없음")
        return

    print(f"  ✓ {len(items)}개. 0.1초 후 시작...")
    time.sleep(0.1)

    screen2      = capture_screen()
    lock_clicked = click_lock_button(screen2)
    if lock_clicked:
        time.sleep(0.3)

    prev_pause = pyautogui.PAUSE
    pyautogui.PAUSE = 0
    try:
        for i,(sx,sy,w,h,lx,ly,method) in enumerate(items):
            if _check_abort():
                break
            print(f"  [{i+1}/{len(items)}] ({sx},{sy}) 방식={method}")
            pyautogui.moveTo(sx, sy)
            pyautogui.mouseDown()
            time.sleep(TRIBUTE_MOUSE_HOLD)
            pyautogui.mouseUp()
            time.sleep(TRIBUTE_CLICK_DELAY)
    finally:
        pyautogui.PAUSE = prev_pause
    print("  완료!")

# ──────────────────────────────────────────────
#  메인
# ──────────────────────────────────────────────

def main():
    print("=" * 62)
    print("  POE2 자동화 툴 v7 (해상도 독립적)")
    print("=" * 62)
    print("  F1  : 인벤토리 Ctrl+클릭")
    print("  F2  : 헌정품 자동 클릭")
    print("  F3  : 인벤토리 그리드 미리보기")
    print("  F4  : 헌정품 감지 미리보기")
    print("  F5  : 인벤토리 캘리브레이션")
    print("  F7  : 제외 칸 설정 GUI")
    print("  F8  : 빈 칸 HSV 측정")
    print("  F9  : 헌정품 캘리브레이션")
    print("-" * 62)
    for f, lbl in [(TEMPLATE_SYMBOL,    "헌정품 아이템 문양"),
                   (TEMPLATE_LOCK,      "헌정품 자물쇠 버튼"),
                   (TEMPLATE_INV_TITLE, "소지품창 타이틀")]:
        ok = "✓" if os.path.exists(f) else "✗ 없음!"
        print(f"  {ok}  {lbl}: {f}")
    print("-" * 62)
    load_inv_config()
    load_tribute_config()
    print("=" * 62)

    keyboard.add_hotkey('f1', inventory_ctrl_click)
    keyboard.add_hotkey('f2', auto_click)
    keyboard.add_hotkey('f3', preview_inventory)
    keyboard.add_hotkey('f4', preview_detection)
    keyboard.add_hotkey('f5', lambda: threading.Thread(target=calibrate_inventory,    daemon=True).start())
    keyboard.add_hotkey('f7', lambda: threading.Thread(target=edit_skip_cells,        daemon=True).start())
    keyboard.add_hotkey('f8', lambda: threading.Thread(target=measure_empty_cell_hsv, daemon=True).start())
    keyboard.add_hotkey('f9', lambda: threading.Thread(target=calibrate_tribute, daemon=True).start())

    print("\n대기 중... (F1~F8 / F9=헌정품캘리브 / 종료=Ctrl+C)")
    try:
        keyboard.wait('f12')
    except KeyboardInterrupt:
        pass
    print("\n종료합니다.")
    sys.exit(0)


if __name__ == "__main__":
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
    main()
