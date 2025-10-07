# Chzzk Recorder

치지직(CHZZK) 스트리머의 방송을 자동으로 녹화하는 Python 스크립트입니다. Docker를 사용하여 백그라운드에서 실행되며, 설정된 스트리머가 방송을 시작하면 자동으로 녹화를 시작하고 종료 시까지 영상을 저장합니다.

## ✨ 주요 기능

- 설정된 스트리머 목록을 주기적으로 확인하여 방송 시작 시 자동 녹화
- Docker 및 Docker Compose를 활용한 간편한 실행 및 관리
- 설정, 로그, 녹화 영상 폴더를 분리하여 관리 용이
- `.ts` 포맷으로 영상 저장

## 🚀 시작하기 (Getting Started)

PC에 [Docker Desktop](https://www.docker.com/products/docker-desktop/)만 설치되어 있으면 됩니다. Python이나 다른 라이브러리를 직접 설치할 필요가 없습니다.

### 1. 리포지토리 클론
```bash
git clone https://github.com/Vueroeruco/chzzk-recorder.git
cd chzzk-recorder
```

### 2. 초기 설정 (최초 1회)

`config.json` 설정 파일과 `session.json` 인증 파일을 생성하기 위해, 아래 명령어로 **설정용 임시 컨테이너**를 실행합니다.

```bash
docker-compose run --rm recorder python3 setup.py
```

- 위 명령어를 실행하면 Docker 환경 안에서 `setup.py`가 시작됩니다.
- 터미널의 안내에 따라 아래 과정을 진행하세요.
  1.  **네이버 아이디/비밀번호 입력**: Chzzk 인증에 사용됩니다.
  2.  **브라우저 로그인**: 자동으로 브라우저가 열립니다. 2단계 인증, 새로운 기기 등록 등 추가 인증이 필요하면 브라우저에서 완료해주세요.
  3.  **녹화 채널 선택**: 로그인 성공 후, 팔로우한 채널 목록에서 녹화를 원하는 채널을 번호로 선택합니다.
  4.  **저장 경로 설정**: 녹화된 영상이 저장될 경로를 지정합니다. (기본값 사용 가능)

- 모든 과정이 끝나면 `config.json`과 `session.json` 파일이 PC의 `chzzk_recorder/config` 폴더에 저장되고, 설정용 임시 컨테이너는 자동으로 삭제됩니다.

### 3. 녹화 프로그램 실행

초기 설정이 완료되었으면, 아래 명령어로 실제 녹화 프로그램을 백그라운드에서 실행합니다.

```bash
docker-compose up -d
```

이제 설정된 채널의 방송 시작을 자동으로 감지하고 녹화를 시작합니다.

> **Note**: `watcher.py`가 6시간마다 자동으로 세션을 갱신하므로, `setup.py`를 다시 실행할 필요는 거의 없습니다. 만약 인증이 계속 실패하는 경우에만 1번의 `docker-compose run` 명령어를 다시 실행하여 `session.json`을 갱신해주세요.

## ⚙️ 관리

-   **실행 중지**
    ```bash
    docker-compose down
    ```

-   **로그 확인**
    ```bash
    docker-compose logs -f
    ```

## 📂 디렉토리 구조

-   `./chzzk_recorder/config`: `config.json` 설정 파일이 위치합니다.
-   `./chzzk_recorder/logs`: 애플리케이션 실행 로그가 저장됩니다.
-   `./chzzk_recorder/recordings`: 녹화된 `.ts` 영상 파일이 저장됩니다.

> **Note**: 위 폴더들은 `docker-compose.yml`의 `volumes` 설정에 따라 PC의 폴더와 실시간으로 연결되어 있습니다. 컨테이너는 항상 내부의 `/app/recordings` 경로에 녹화하지만, 실제 파일은 PC의 `./chzzk_recorder/recordings` 폴더에 저장됩니다.

### 💡 녹화 저장 위치 변경하기

녹화 파일을 다른 폴더(예: `D:\MyVideos`)에 저장하고 싶다면, `docker-compose.yml` 파일을 열어 `volumes` 섹션의 다음 부분을 수정하세요.

```yaml
# docker-compose.yml

services:
  recorder:
    # ... (다른 설정들)
    volumes:
      - ./chzzk_recorder/config:/app/config
      - ./chzzk_recorder/logs:/app/logs
      # 아래 줄의 ':' 앞 부분을 원하는 PC 폴더 경로로 변경하세요.
      - ./chzzk_recorder/recordings:/app/recordings # 이 줄을 수정
```

예를 들어 `D:\MyVideos`에 저장하려면 아래와 같이 변경합니다.

```yaml
      - D:\MyVideos:/app/recordings
```
