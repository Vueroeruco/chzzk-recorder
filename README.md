# Chzzk Recorder

치지직(CHZZK) 스트리머의 방송을 자동으로 녹화하는 Python 스크립트입니다. Docker를 사용하여 백그라운드에서 실행되며, 설정된 스트리머가 방송을 시작하면 자동으로 녹화를 시작하고 종료 시까지 영상을 저장합니다.

## ✨ 주요 기능

- 설정된 스트리머 목록을 주기적으로 확인하여 방송 시작 시 자동 녹화
- Docker 및 Docker Compose를 활용한 간편한 실행 및 관리
- 설정, 로그, 녹화 영상 폴더를 분리하여 관리 용이
- `.ts` 포맷으로 영상 저장

## 🚀 설치 및 실행 방법

이 프로젝트는 Docker 사용을 권장합니다.

1.  **리포지토리 클론**
    ```bash
    git clone https://github.com/Vueroeruco/chzzk-recorder.git
    cd chzzk-recorder
    ```

2.  **설정 파일 준비**
    - `chzzk_recorder/config/` 디렉토리로 이동합니다.
    - `config.json.example` 파일을 복사하여 `config.json` 파일을 생성합니다.
    - `config.json` 파일을 열어 아래 설명에 맞게 수정합니다.
      - `streamers`: 녹화할 스트리머의 ID 목록을 추가합니다. (예: `"c1b852c6d15813a81f851c4a574c7382"`)
      - `output_dir`: 녹화 파일이 저장될 컨테이너 내부 경로입니다. (기본값: `/app/recordings`)
      - `log_dir`: 로그 파일이 저장될 컨테이너 내부 경로입니다. (기본값: `/app/logs`)
      - `poll_interval_seconds`: 방송 상태를 확인하는 주기(초)입니다.

3.  **Docker 컨테이너 실행**
    - 프로젝트의 최상위 디렉토리( `docker-compose.yml` 파일이 있는 곳)로 돌아옵니다.
    - 아래 명령어를 실행하여 Docker 컨테이너를 백그라운드에서 시작합니다.
    ```bash
    docker-compose up -d
    ```

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

> **Note**: `docker-compose.yml` 설정에 따라 위 폴더들은 로컬 환경의 동일한 이름의 폴더와 연결(마운트)되어 있어, 컨테이너 외부에서도 파일에 접근할 수 있습니다.
