# Chzzk Recorder 작업 요약 및 변경 사항

본 문서는 최근 작업 내역과 구성/운영 가이드를 정리한 문서입니다.

## 실행/환경
- Docker 기반 구동 확인: `docker compose up -d --build`
- 컨테이너: `chzzk_recorder` (이미지 `new_4-recorder`)
- 로그 확인: `docker logs -f chzzk_recorder`
- 내부 경로
  - 녹화: `/app/recordings`
  - 로그: `/app/logs/YYYYMMDD`

## 핵심 변경
- ffmpeg 폴백 제거, N_m3u8DL-RE 단일 파이프라인으로 통일
  - 실시간 TS 저장: `--live-real-time-merge` + `--live-pipe-mux`
  - 병렬 옵션: `-mt` + `--thread-count <n>`
  - 헤더 전달(`--header`) 유지, ANSI 제어문자 비활성화(`--no-ansi-color`)
- MP4 리먹스 제거: 스트림 종료 시 MP4 변환 단계 삭제(타임라인 꼬임 방지)
- 성인(19세) 방송 녹화 지원: `session.json`의 `NID_SES` 쿠키 기반 접근

## 안정화/신규 기능
1) 빠른 재시작(fast restart)
- TS 파일 크기 증가가 멈춘 경우 더 짧은 임계값으로도 재시작
- 설정: `fast_restart_seconds`(기본 30초), `stall_restart_seconds`와 함께 동작

2) 메타데이터 사이드카 저장
- 녹화 시작 시 `<basename>.meta.json` 생성
- 포함 정보: `channelId`, `videoId`, `channelName`, `liveTitle`, `m3u8_url`, `started_at`, `output`, `log_dir`
- 위치: 녹화 파일(.ts)와 동일 폴더

3) 일일 정리(클린업)
- 의도: 스트리머가 다시보기를 올린 영상은 로컬 저장 유지 불필요 → 삭제
- 기준: 메타의 `videoId`가 채널 VOD 목록 API에서 발견되면 로컬 TS/메타 삭제
- 스케줄: 하루 1회(`cleanup_hour` 이후 1회만) 실행
- 로그: `/app/logs/YYYYMMDD/cleanup.log` (JSON Lines)
- API: `GET https://api.chzzk.naver.com/service/v1/channels/{channelId}/videos`

## 코드 변경(주요 파일)
- chzzk_recorder/recorder.py
  - ffmpeg 폴백 제거
  - N_m3u8DL-RE 옵션 수정(실시간 TS 저장)
  - 사이드카 메타 저장 추가
- chzzk_recorder/watcher.py
  - 빠른 재시작 로직 추가
  - 일일 정리 스케줄링 및 삭제/로그 기록 추가
  - `channelId`를 recorder에 전달
- chzzk_recorder/chzzk_api.py
  - `get_channel_videos(channel_id, page, size, sort)` 추가(VOD 조회)
- chzzk_recorder/setup.py
  - `config.json` 생성 시 실제 런타임에 쓰는 기본 옵션 포함
- chzzk_recorder/config/config.json.example
  - 예시 설정에 동일 옵션 반영

## 설정 스키마(주요 키)
- `TARGET_CHANNELS`: 모니터링할 채널 ID 배열
- `POLLING_INTERVAL_SECONDS`: 폴링 주기(초), 기본 30
- `use_n_m3u8dlre`: N_m3u8DL-RE 사용 여부, 기본 true
- `n_m3u8dlre_threads`: 병렬 스레드 수, 기본 8
- `on_start_previous`: 기존 파일 정책(`ignore|archive|delete`), 기본 `ignore`
- `archive_dir`: `archive` 사용 시 보관 경로, 기본 `/app/recordings_archive`
- `session_path`: 세션 파일 경로, 기본 `/app/config/session.json`
- `stall_restart_seconds`: 일반 중단 임계값(초), 기본 180
- `fast_restart_seconds`: 빠른 재시작 임계값(초), 기본 30
- `cleanup_enabled`: 일일 정리 실행 여부, 기본 true
- `cleanup_hour`: 일일 정리 수행 시각(시), 기본 5

## 운용 가이드
- 실시간 상태 확인: `docker logs -f chzzk_recorder`
- 최근 NMD 로그: `/app/logs/YYYYMMDD/*_nmd.log`
- 정리 로그: `/app/logs/YYYYMMDD/cleanup.log`
- 수동 시작(디버그): `python /app/config/manual_start.py <channel_id>` (컨테이너 내부)

## 보안/주의 사항
- N_m3u8DL-RE는 `--header "Cookie: ..."`를 인자로 받으므로, 컨테이너 내부 프로세스 목록으로 쿠키가 노출될 수 있음(운영 환경에서 접근 권한 관리 권장)
- `ba.uuid`는 인증 토큰이 아닌 장치 식별자 성격이며, 세션 쿠키(`NID_SES` 등)는 `session.json`에서만 로드(하드코딩하지 않음)

## 한계/향후 개선
- VOD 조회는 기본 1페이지(size 50)만 확인 → 장기 방송/딜레이 시 페이지 확장 필요 시 파라미터 튜닝/페이징 루프 도입 고려
- 일일 정리의 시간대는 로컬 시간 기준 → 타임존 명시 또는 크론 스타일 스케줄러 고려 가능
- 쿠키 노출 저감: 별도 프록시/환경변수 주입/프로세스 인자 마스킹 등 보완책 검토 가능

## 변경 이력(요약)
- N_m3u8DL-RE 단일화, TS 실시간 저장, MP4 리먹스 제거
- 빠른 재시작/일일 정리/사이드카 메타 추가
- setup/config 예시 갱신

