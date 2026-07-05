# AutoClickHelper (POE2)

Path of Exile 2 인벤토리/헌정품(Tribute) 자동 클릭을 도와주는 Windows용 GUI 툴입니다.

## 다운로드

빌드된 실행 파일(`AutoClickHelper.exe`)은 소스로 배포하지 않고 [Releases](../../releases) 페이지에서 버전별로 받을 수 있습니다.
바로 실행하고 싶다면 최신 릴리스의 `AutoClickHelper.exe`만 받으면 됩니다 (Python 설치 불필요).

## 주요 기능

- **인벤토리 자동 클릭** — 소지품창에서 아이템만 골라 Ctrl+클릭
- **헌정품(Tribute) 자동 클릭** — 헌정품 아이템 자동 감지 후 클릭
- **오토클릭 토글** — 지정 키/마우스 버튼으로 자동 클릭 On/Off
- **키 연동(Key Link)** — 특정 키를 누르면 다른 키를 함께 입력
- **클릭 반복** — 지정 마우스 버튼 입력 시 클릭 반복
- 모든 단축키는 GUI에서 자유롭게 변경 가능하며 `hotkey_config.json` 등에 저장됩니다.

## 기본 단축키

| 기능 | 기본 키 |
|---|---|
| 인벤토리 클릭 | F1 |
| 헌정품 클릭 | F2 |
| Ctrl+Shift 클릭 | SHIFT+F3 |
| 오토클릭 토글 | F6 |

GUI에서 각 항목의 키를 클릭하고 원하는 키를 눌러 변경할 수 있습니다.

## 소스에서 직접 실행하기

```bash
pip install pyautogui opencv-python numpy Pillow keyboard pywin32 mouse
python auto_click_helper_ui.py
```

`poe2_tribute_clicker.py`, `tribute_symbol.png`은 `auto_click_helper_ui.py`와 같은 폴더에 있어야 합니다.

## 직접 빌드하기 (exe)

```bash
build.bat
```

PyInstaller로 `dist/AutoClickHelper.exe`를 생성합니다.

## 주의사항

- Windows 전용이며, 일부 기능(키보드 훅)은 관리자 권한이 필요할 수 있습니다.
- 게임 클라이언트 화면 해상도/UI 배치에 따라 F5(인벤토리 캘리브레이션), F9(헌정품 캘리브레이션)로 보정이 필요할 수 있습니다.
- 게임 매크로/자동화 관련 사용은 게임 운영정책을 따르며, 사용에 따른 제재 등은 사용자 책임입니다.
