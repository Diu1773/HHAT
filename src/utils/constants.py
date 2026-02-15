"""프로젝트 전역 상수"""

# 21cm HI 선 정지 주파수 (MHz)
HI_REST_FREQ_MHZ = 1420.40575177

# 광속 (km/s)
C_KMS = 299792.458

# 기본 관측지 프리셋 (대한민국 주요 관측지)
SITE_PRESETS = {
    "서울": {"lat": 37.5665, "lon": 126.9780, "height": 38.0},
    "대전": {"lat": 36.3504, "lon": 127.3845, "height": 70.0},
    "보현산천문대": {"lat": 36.1648, "lon": 128.9766, "height": 1124.0},
    "소백산천문대": {"lat": 36.9333, "lon": 128.4561, "height": 1390.0},
    "사용자 지정": {"lat": 0.0, "lon": 0.0, "height": 0.0},
}

# 관측 타입
OBS_TYPE_KEYWORDS = {
    "SOU": ["_SOU", "_sou", "_SOURCE", "_source"],
    "AMB": ["_AMB", "_amb", "_AMBIENT", "_ambient"],
    "SKY": ["_SKY", "_sky"],
}

# QC 임계값
QC_THRESHOLDS = {
    "spike_zscore": 5.0,
    "psd_min_db": -120.0,
    "psd_max_db": 20.0,
    "max_nan_ratio": 0.01,
}
