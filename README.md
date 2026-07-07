# MANTA Anti-Virus (프로토타입)

## 요약

- 이 저장소는 Python 기반 런처를 중심으로 한 AV 프로토타입입니다.
- 목적: 인터랙티브 런처(터미널 + 반투명 GUI) + 네이티브 모듈(Go/Rust)로 확장 가능한 안티바이러스 를 제공.

## 현재 구현된 항목

- Python 런처 (src/launcher/main.py)
  - 통합 인터페이스: ANSI 터미널 + Tkinter GUI(반투명 창)
  - 상단 아스키 배너(실시간 수직 그라데이션, 라인 단위 색상)
  - 하단 입력창에서 명령 실행, 출력은 누적 표시
  - 명령: scan, scan-async, monitor start|stop, quarantine, db add/remove/list, status, logs, save-logs, help, exit
  - 로컬 해시 DB 연동: db/virus_db.txt 사용, db add/remove 명령으로 수정 가능
  - DLL 준비: dist/manta_scanner.dll, dist/manta_monitor.dll 자동 로드 시도
  - 트레이(pystray) 지원 및 X 동작(숨김/최소화/트레이 유지) 처리
  - Windows에서 콘솔 없이 실행하려고 pythonw로 자동 재실행 시도

- 로컬 DB
  - 경로: db/virus_db.txt (우선 사용), 루트 virus_db.txt는 호환용으로 fallback
  - 형식: 한 줄에 하나의 SHA256(예: sha256:<hex> 또는 <64hex>)

## 미구현(플랜)

- 네이티브 모듈
  - Go: manta_scanner (ScanPath, QuarantineFile, FreeResult)
  - Rust: manta_monitor (MonitorStart, GetEvent, MonitorFreeResult)
- 패키징
  - PyInstaller 빌드(권장: --noconsole, --onefile)
  - build.sh로 Go/Rust DLL 빌드 자동화
- 테스트
  - fake-scan / test 스크립트로 DLL 없이 전체 플로우 시뮬레이션

## 간단 사용 방법

1) 의존 설치(선택적)
   - `pip install -r requirements.txt`  # pystray, Pillow 등
2) 런처 실행
   - 개발 중: `python src/launcher/main.py`
   - 윈도우에서 콘솔 없이 실행하려면: `pythonw src/launcher/main.py`
3) 주요 명령 예
   - `db list`
   - `db add sha256:<hex>`
   - `scan .`
   - `quarantine`

## 테스트/디버그 팁

- 모듈 미존재 시 scan 명령은 결과를 반환하지 않습니다. fake-scan 명령(추후 추가)로 시뮬레이션 가능.
- db에 테스트 해시 추가 후 scan(더미 결과)에서 매칭 동작을 확인하세요.

## 보안 및 주의

- 해시 목록만 저장하세요. 악성 샘플 자체는 저장/실행하지 마시기 바랍니다.
- 공개 피드 해시는 검증 후 사용하세요(오탐 위험).

## 개발/기여

- src/launcher/main.py가 핵심입니다. 모듈 스텁이나 테스트 스크립트 커밋 환영합니다.
- 기여는 편하게 해주시면 감사합니다!!
