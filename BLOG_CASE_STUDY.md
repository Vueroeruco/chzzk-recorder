# CHZZK 레코더 개선기: 안정적 TS 녹화, 자동 정리, 운영 편의까지

이 문서는 본 프로젝트를 개선하면서 “무엇을, 왜, 어떻게” 바꿨는지와 그 결과를 블로그/포트폴리오 형식으로 정리한 기록이다. 실제 운영에서 맞닥뜨린 문제를 진단하고, 설계·구현·검증까지 이어지는 과정을 담았다.

## 배경과 목표
- 배경: 특정 스트리머의 라이브 방송을 자동 녹화해 보관하다가, 스트리머가 VOD(다시보기)를 게시하면 로컬 저장본을 지워 공간을 절약하고자 했다.
- 초기 상태: ffmpeg 기반 폴백과 N_m3u8DL-RE가 혼용되어 있었고, 실시간 MP4 병합/종료 후 MP4 리먹스가 섞여 타임라인이 꼬이는 사례가 발생.
- 목표
  - 안정적인 실시간 TS 저장으로 전환해 타임라인 문제 제거
  - 19+(성인) 방송도 정상 처리
  - 방송 종료 후 “VOD가 게시되면 로컬 파일 자동 삭제” 자동화
  - 중단/끊김 발생 시 빠르게 녹화를 재시작하는 복원력 확보

## 문제 진단
- 현상: 컨테이너 로그에서 녹화 프로세스가 반복적으로 시작/종료. N_m3u8DL-RE가 Usage만 출력하고 종료하는 정황 확인.
- 원인1(옵션 불일치): `--concurrent-download <num>`처럼 도구와 맞지 않는 인자를 사용 중. 최신 N_m3u8DL-RE는 `-mt` 플래그와 `--thread-count` 조합을 사용해야 한다.
- 원인2(타임라인 꼬임): 실시간 병합 중 MP4 파일 생성, 종료 시 ffmpeg로 추가 리먹스까지 이루어지면서 PTS/헤더가 중복 처리되어 타임라인이 뒤틀릴 여지가 있었다.

## 설계 변경 요약
1) 녹화 파이프라인 단일화(핵심)
- ffmpeg 폴백 제거 → N_m3u8DL-RE만 사용
- 실시간 TS 저장: `--live-real-time-merge + --live-pipe-mux`
- 병렬 다운로드: `-mt --thread-count <N>`
- 헤더 전달: `--header`로 UA/Origin/Referer/Cookie 등

2) 형식 및 후처리 정책 변경
- 실시간 저장 확장자: TS로 고정
- 종료 후 MP4 리먹스 단계 삭제(타임라인 꼬임 제거)

3) 성인(19+) 방송 처리
- `session.json`의 `NID_SES` 포함 여부 확인 후 접근
- 쿠키는 실행 시점에만 로드(하드코딩 없음), `ba.uuid`는 없을 때 대체 장치 ID를 사용

4) 복원력(Resilience) 강화
- 파일 크기 성장 모니터링으로 stall 감지
- `fast_restart_seconds`(기본 30s)로 더 빠른 재시작 판단

5) 자동 정리(클린업)
- 녹화 시작 시 사이드카 메타(`.meta.json`) 저장: channelId/videoId 등 기록
- 매일 1회 VOD 목록 API 조회
- 동일 videoId가 VOD 목록에 존재하면 TS 및 메타 삭제
- 정리 결과를 JSON lines 형태의 `cleanup.log`에 기록

## 구현 상세
### A. Docker/런타임
- `docker-compose.yml`로 `/app/config`, `/app/logs`, `/app/recordings` 볼륨 마운트
- 베이스 이미지: Playwright Python + ffmpeg + N_m3u8DL-RE 바이너리 설치
- 컨테이너 구동 시 `watcher.py`가 메인 루프 수행

### B. N_m3u8DL-RE 호출 정정
- 잘못된 옵션 제거, 아래 인자로 통일:
  - `--live-real-time-merge` + `--live-pipe-mux`
  - `-mt --thread-count <threads>`
  - `--save-dir`, `--save-name`
  - `--no-ansi-color`
  - `--header`로 쿠키/UA 등 전달
- 결과: “시작 직후 종료” 문제 해소, 안정적인 TS 파일 생성 확인

### C. 타임라인 꼬임 해소
- MP4 실시간 병합 및 종료 후 리먹스 흐름을 제거
- TS로 직저장해 세그먼트/타임스탬프 꼬임 가능성 최소화

### D. 19+ 방송 처리
- `chzzk_api.py`가 `session.json`의 쿠키로 헤더 구성
- `ba.uuid`는 없을 때 대체 UUID 사용(인증 토큰과 무관)
- `NID_SES` 존재 시 성인 채널 접근 가능

### E. 메타데이터 사이드카
- `recorder.py`: 녹화 시작 시 `<basename>.meta.json` 생성
- 필드: `channelId`, `videoId`, `channelName`, `liveTitle`, `m3u8_url`, `started_at`, `output`, `log_dir`
- 목적: 정리(클린업)과 트레이싱에 활용

### F. 일일 정리(클린업)
- `watcher.py` 메인 루프에서 하루 1회 스케줄
- `chzzk_api.py.get_channel_videos()`로 VOD 목록 취득
- `.meta.json`의 `videoId`와 목록의 `videoId`가 일치하면 TS/메타 삭제
- `/app/logs/YYYYMMDD/cleanup.log`에 JSON lines로 기록(삭제 사유 포함)

### G. 빠른 재시작(중단 감지)
- `stall_restart_seconds`와 별도로 `fast_restart_seconds` 도입(기본 30s)
- 파일 크기 성장이 없을 때 더 짧은 임계값으로도 재시작
- “중간 끊김” 상황에서 수 초 내 복구되는 체감을 확보

### H. 설정/셋업 개선
- `setup.py`가 생성하는 `config.json`에 실제 런타임 키 포함
  - `use_n_m3u8dlre`, `n_m3u8dlre_threads`, `on_start_previous`, `archive_dir`
  - `session_path`, `stall_restart_seconds`, `fast_restart_seconds`
  - `cleanup_enabled`, `cleanup_hour`
- `config.json.example`도 동일 스키마로 갱신

## 운영/검증
- 로그 관찰로 “녹화 시작 → 진행 → 종료” 플로우의 안정성 확인
- 컨테이너 내부에서 디렉터리/파일 용량 증가 확인(실시간 TS 증가)
- 성인 채널(19+) 실제 스트림에 대해 TS 생성/증가 검증
- 일일 정리 스케줄은 지정 시각 이후 1회만 실행(개발 단계에서는 수동 호출로 로직 검증)

## 보안 고려사항
- 프로세스 인자에 `--header "Cookie: ..."`가 포함되므로, 컨테이너 내부 프로세스 나열 시 쿠키 노출 가능 → 운영 접근 권한 최소화 권장
- 세션 쿠키는 파일에서만 로드하며 코드 하드코딩 없음
- `ba.uuid` 디폴트는 인증 토큰이 아니며, 장치 식별 보조용 값

## 트레이드오프와 대안
- TS만 유지: 편의성(재생 호환성) 측면에서 MP4가 더 친숙하지만, 안정성과 단순화를 위해 TS를 선택
- VOD 동기 삭제: VOD 지연 게시/편집 등 정책 변화에 대비해 “보존 기간+삭제” 같은 정책 옵션을 확장 가능
- 빠른 재시작: 과민 반응을 막기 위해 `fast_restart_seconds`를 보수적으로 설정(기본 30s). 환경에 맞춰 튜닝 권장

## 성과
- 녹화 안정성 향상: 시작 직후 종료 문제 해소, 파일 연속성 개선
- 타임라인 꼬임 제거: 실시간 MP4/리먹스 제거로 PTS 꼬임 사례 급감
- 저장소 효율: VOD 게시 영상 자동 삭제로 디스크 사용량 절감
- 운영 편의: 설정 스키마/셋업 통일 및 로그/사이드카로 추적성 확보

## 향후 개선
- VOD 페이징 확장: 오래된 영상 매칭을 위해 페이지 루프(예: 최대 N페이지) 도입
- 쿠키 노출 저감: 런처 스크립트/프록시로 헤더 전달을 은닉하거나 마스킹
- 정리 정책 다변화: 아카이브 이동 후 주기 삭제, 보존 기한, 예외 채널 리스트 등
- 모니터링: Prometheus exporter/단순 health endpoint로 상태 외부 노출

## 마무리
실제 운영 문제(타임라인 꼬임, 즉시 종료, 디스크 낭비)를 구체적으로 진단하고, 파이프라인 단순화와 운영 자동화를 통해 안정성과 편의성을 모두 끌어올렸다. 향후에도 운영 데이터를 바탕으로 정리 정책/복원력/보안을 점진적으로 강화할 계획이다.

