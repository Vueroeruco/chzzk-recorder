# CHZZK 라이브(HLS) 녹화 트러블슈팅 & 실행 가이드

> 목적: Docker 컨테이너 환경에서 `ffmpeg`로 CHZZK **라이브** HLS 스트림(fMP4/TS 혼재 가능)을 **직접 녹화**할 때 필요한 최소 옵션, 오류 원인, 점검 루틴을 한 방에 정리했습니다.  
> 단일 파일로 읽히도록 작성되어 Gemini/CLI 툴 입력에 적합합니다.

---

## TL;DR (요약)

- **필수 설정 3종**  
  1) **요청 헤더/쿠키**를 `-headers`(또는 `-cookies`, `-user_agent`, `-referer`)로 정확히 전달  
  2) 세그먼트 확장자가 `.m4s/.m4v` 등일 때 **HLS 디먹서 화이트리스트**를 풀기 위해 `-allowed_extensions ALL` 추가  
  3) 라이브가 **fMP4**이면 매니페스트에 있는 **`#EXT-X-MAP`(init)** 을 올바르게 받아야 함

- **DRM 식별**: 매니페스트에 `#EXT-X-KEY:METHOD=SAMPLE-AES, KEYFORMAT="com.apple.streamingkeydelivery"`가 보이면 **FairPlay DRM** 이라서 일반 ffmpeg로 **복호화 불가**. (AES-128은 가능)

- `yt-dlp`는 **라이브에서 TS(mpegts)** 로 저장하는 `--hls-use-mpegts`가 **기본 활성**입니다. ffmpeg 단독으로도 동일 개념(직결 다운로드 + 리멕스)로 처리 가능합니다.

---

## 1) ffmpeg로 “직결 녹화”할 때의 최소 커맨드

> 아래는 **라이브 3초만 테스트**하는 예시입니다. 실제 운영 시 `-t 3` 제거.

```bash
ffmpeg \
  -headers $'Cookie: <세션쿠키들>\r\nReferer: https://chzzk.naver.com/\r\nOrigin: https://chzzk.naver.com\r\nUser-Agent: Mozilla/5.0\r\n' \
  -allowed_extensions ALL \
  -rw_timeout 15000000 \
  -i "https://.../playlist.m3u8?...(서버에서 받은 m3u8 URL)..." \
  -c copy -y recordings/test.ts
```

- **핵심 포인트**
  - `-headers` : 서버가 요구하는 **쿠키/리퍼러/UA** 를 그대로 넣어 인증 실패를 방지  
  - `-allowed_extensions ALL` : HLS 디먹서가 **`.m4s/.m4v` 등 fMP4 조각**을 거부하지 않도록 허용  
  - `-c copy` : **트랜스코딩 없이** 즉시 저장(빠르고 안정적)  
  - 출력 컨테이너는 **TS(mpegts)** 가 라이브에 더 안전. 사후에 필요하면 MP4로 리멕스.

---

## 2) 왜 ffmpeg가 “Invalid data found”로 죽을까? (원인 정리)

1. **확장자 화이트리스트 차단**  
   - 라이브가 **fMP4(HLS+CMAF)** 인 경우, 세그먼트 확장자가 `.m4s/.m4v` 입니다.  
   - HLS 디먹서는 기본적으로 **허용 확장자만 접근**하도록 “picky” 모드가 켜져 있어,  
     **`-allowed_extensions ALL`** 을 주지 않으면 첫 세그먼트에서 **Invalid data**가 납니다.

2. **초기화 조각(init) 누락**  
   - fMP4는 플레이리스트에 **`#EXT-X-MAP:URI="init.mp4"`** 로 초기화 구간을 명시합니다.  
   - 이 **init 조각이 404/권한거부/헤더미스**면 첫 미디어 조각을 해석하지 못해 실패합니다.

3. **헤더/쿠키 미전달**  
   - CHZZK는 **쿠키/리퍼러/UA** 를 체크합니다.  
   - `-headers` 혹은 `-cookies`, `-user_agent`, `-referer`를 **정확히** 넣어야 합니다.

4. **실시간 특성(라이브 윈도)**  
   - 아주 이른/늦은 세그먼트를 잡으려다 실패할 수 있습니다. 처음엔 **자연스러운 최신 구간**으로 들어가세요.  
   - 필요 시 `-live_start_index -3` 같은 옵션(플레이리스트 끝에서 n개 이전)도 검토.

---

## 3) VOD vs 라이브, 그리고 `--hls-use-mpegts` 의미

- 많은 다운로더(예: yt-dlp)는 **라이브 시 TS 컨테이너**로 저장하도록 기본값이 설정되어 있습니다.  
  - 이유: TS는 **분절 저장/재시작**에 강하고, **중간 끊김** 시 복구가 상대적으로 쉽습니다.  
  - ffmpeg 단독 사용에서도 **입력은 fMP4/TS 상관없이** 받아오고, **출력은 TS** 로 두는 게 안전합니다.  
- 녹화 후 필요하면 **MP4로 리멕스**:  
  ```bash
  ffmpeg -i input.ts -c copy output.mp4
  ```

---

## 4) DRM(암호화) 식별 체크리스트

- 매니페스트에서 아래가 보이면 **FairPlay DRM → 일반 ffmpeg 불가**  
  ```
  #EXT-X-KEY:METHOD=SAMPLE-AES,KEYFORMAT="com.apple.streamingkeydelivery",...
  ```
- **가능(일반 복호화)**: `METHOD=AES-128`(키 URI에서 key를 받아 CBC로 세그먼트 전체 복호화)  
- **불가(플레이어 전용 DRM)**: `METHOD=SAMPLE-AES` (+ KEYFORMAT이 FairPlay 등)  
- 즉, 실패 원인이 “헤더/확장자/초기화조각” 문제가 아니고 위 **DRM 시그널**이면, **다운로드만으로 재생 파일 만들 수 없음**.

---

## 5) 점검 루틴 (빠른 진단 순서)

1. **m3u8 전문 저장** 후, `#EXT-X-MAP` 유무/경로/쿼리 파라미터 확인  
2. **첫 init/first segment를 curl로 직접 GET** → **HTTP 200**인지, **쿠키/리퍼러/UA** 동일하게 전달  
3. ffmpeg **단독 커맨드**로 3~5초 캡처 테스트  
4. 여전히 실패면 `-report` 로 ffmpeg 로그 저장 후 **첫 오류 이전 행**에 나타나는 URL/포맷 확인  
5. 매니페스트에 **SAMPLE-AES + KEYFORMAT** 보이면 **DRM 케이스**로 분류

---

## 6) 실전 예시 (의사코드 + 커맨드)

### (A) 세션에서 쿠키 문자열 만들기 (파이썬 예시)

```python
cookies = {"NID_SES": "...", "NNB": "..."}  # 세션에서 가져옴
cookie_string = "; ".join([f"{k}={v}" for k,v in cookies.items()])
headers_block = (
    f"Cookie: {cookie_string}\\r\\n"
    "Referer: https://chzzk.naver.com/\\r\\n"
    "Origin: https://chzzk.naver.com\\r\\n"
    "User-Agent: Mozilla/5.0\\r\\n"
)
```

### (B) ffmpeg 단독 녹화 (라이브, TS 컨테이너로 저장)

```bash
ffmpeg \
  -headers "$headers_block" \
  -allowed_extensions ALL \
  -rw_timeout 15000000 \
  -i "$M3U8_URL" \
  -c copy -f mpegts -y "recordings/$(date +%Y%m%d_%H%M%S)_channel.ts"
```

### (C) 사후 리멕스 (선택)

```bash
ffmpeg -i "recordings/20251003_123456_channel.ts" -c copy "recordings/20251003_123456_channel.mp4"
```

---

## 7) 히토미다운로더 방식과의 교집합(아이디어)

- 히토미다운로더는 **VOD** 성격의 `.m3u8`에서 **조각을 직접 병렬 다운로드** 후 **로컬 병합**하는 루틴이 핵심입니다.  
- 라이브도 **원리는 동일**:  
  1) m3u8 파싱 → 2) `EXT-X-MAP`(init) 먼저 GET → 3) **가장 최근 세그먼트들**만 순차/병렬 GET → 4) **TS로 직결 저장**  
- 다만, **DRM/HLS-CMAF(fMP4)** 의 규칙을 위처럼 정확히 지켜야 초기화/확장자 문제로 **ffmpeg가 죽지 않습니다.**

---

## 참고 자료(문서 원문 링크)

- ffmpeg **HTTP 프로토콜 옵션**(headers/cookies/referer/user_agent 등):  
  https://ffmpeg.org/ffmpeg-protocols.html#http

- ffmpeg **HLS 디먹서** 옵션(allowed_extensions, extension_picky 등):  
  https://man.archlinux.org/man/ffmpeg-formats.1.en#hls

- HLS **EXT-X-MAP** (fMP4 초기화) 정의:  
  https://datatracker.ietf.org/doc/html/rfc8216

- **FairPlay** 표식 예시(SAMPLE-AES + KEYFORMAT):  
  https://developer.apple.com/documentation/http-live-streaming/using-content-protection-systems-with-hls

- yt-dlp `--hls-use-mpegts` (라이브 기본 활성 설명):  
  https://man.archlinux.org/man/yt-dlp.1.en#--hls-use-mpegts