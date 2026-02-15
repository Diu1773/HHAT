# HHAT

HHAT는 **HI Horn Analysis Tool** (21cm 중성수소 관측 GUI)입니다.  
`관측` 탭에서 RTL-SDR로 데이터를 수집하고, `분석` 탭에서 단계별 파이프라인으로 보정/피팅/물리량 계산/맵 시각화를 수행합니다.

## 주요 기능

- PySide6 기반 데스크톱 GUI
- RTL-SDR 관측 및 FITS 저장 (`raw_observation.fits`)
- 13단계 분석 파이프라인
- RFI 마스킹, baseline 처리, Y-factor 교정
- 속도축 변환, 좌표/LSR 관련 계산, 피크 검출
- 다성분 프로파일 피팅 (gaussian/skewed/voigt, MCMC 옵션)
- 물리량 계산 (`∫Tdv`, `N_HI`) 및 은하지도(빔 커버리지) 시각화
- 단계별 캐시/자동 내보내기 (`exports/latest`)

## 폴더 구조

- `main.py`: 앱 실행 진입점
- `src/observe/`: 관측 탭 및 SDR 제어
- `src/analysis/`: Step 1~13 분석 UI
- `src/core/`: 피팅/교정/속도/물리량/캐시 등 핵심 로직
- `src/models/`: 데이터 모델 및 프로젝트 상태
- `data/`: 관측 예제/결과 데이터
- `전파관측/`: RTL-SDR 관련 DLL/유틸 파일

## 요구 사항

- Python 3.10+
- RTL-SDR 장비 (관측 기능 사용 시)
- `requirements.txt` 의존성

## 설치

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

## 실행

```bash
python main.py
```

## 분석 파이프라인(요약)

1. 데이터 로딩
2. 타입 분류(SOU/AMB/SKY)
3. 메타데이터 입력
4. QC
5. 전처리(RFI/스무딩)
6. Baseline/Y-factor
7. 속도축 변환
8. LSR/좌표
9. 피크 검출
10. 프로파일 피팅
11. 물리량 계산
12. 자동 저장 확인
13. 은하지도 맵

## 결과 파일

- `meta.json`: 관측 메타데이터
- `processing_state.json`: 단계 상태/피팅/피크 등
- `processing_cache.npz`: 중간 배열 캐시
- `exports/latest/`: `result.csv`, `fit.json`, `meta.json`, `peaks.json`

## 참고

- 현재 저장소는 연구/실험용 구성입니다.
- 관측/교정 품질은 AMB 촬영 방식, 메타데이터 정확도, RFI 환경에 크게 영향을 받습니다.
