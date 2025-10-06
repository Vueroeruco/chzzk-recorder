# Docker 테스트 실행 가이드

이 문서는 PC 재부팅 후 Docker 환경이 정상화되었을 때, 치지직 녹화 프로그램을 테스트하기 위한 Docker 명령어들을 안내합니다.

`docker-compose` 대신 기본적인 `docker` 명령어를 사용하여 한 단계씩 실행하는 것을 권장합니다.

---

## 사전 준비

1.  **Docker Desktop 실행**: PC에서 Docker Desktop이 정상적으로 실행되고 있는지 확인합니다.
2.  **터미널 열기**: 이 프로젝트의 루트 디렉토리(`new_4`)에서 터미널(PowerShell, CMD 등)을 엽니다.

---

## 1단계: Docker 이미지 빌드

먼저 `Dockerfile`을 기반으로 컨테이너를 실행할 수 있는 이미지를 빌드합니다. 이 과정은 프로젝트의 모든 소스 코드와 의존성을 이미지 안에 패키징합니다.

```bash
docker build -t chzzk_recorder_image .
```

- `-t chzzk_recorder_image`: 빌드된 이미지에 `chzzk_recorder_image`라는 태그(이름)를 붙입니다.
- `.`: 현재 디렉토리의 `Dockerfile`을 사용하라는 의미입니다.

---

## 2단계: Docker 컨테이너 실행

빌드된 이미지를 사용하여 실제 컨테이너를 실행합니다. 컨테이너는 격리된 환경에서 실행되는 프로그램의 인스턴스입니다.

```bash
docker run --name chzzk_recorder_container -d -v "$(pwd)/chzzk_recorder/config:/app/config" -v "$(pwd)/chzzk_recorder/logs:/app/logs" -v "$(pwd)/chzzk_recorder/recordings:/app/recordings" chzzk_recorder_image
```

- `--name chzzk_recorder_container`: 컨테이너에 `chzzk_recorder_container`라는 고유한 이름을 부여합니다. 나중에 로그를 확인하거나 컨테이너를 중지할 때 이 이름을 사용합니다.
- `-d`: 컨테이너를 백그라운드(detached mode)에서 실행합니다. 이 옵션 덕분에 터미널이 멈추지 않습니다.
- `-v "$(pwd)/...:/app/..."`: 로컬 컴퓨터의 폴더와 컨테이너 내부의 폴더를 연결(볼륨 마운트)합니다.
    - `config` 폴더 연결: 컨테이너가 로컬의 `session.json` 파일을 읽을 수 있게 합니다.
    - `logs` 폴더 연결: 컨테이너 내부에서 생성된 로그 파일을 로컬에서 즉시 확인할 수 있게 합니다.
    - `recordings` 폴더 연결: 녹화된 영상(`.ts` 파일)이 로컬 컴퓨터에 저장되게 합니다.
- `chzzk_recorder_image`: 이전에 빌드한 이미지의 이름입니다.

> **참고:** `$(pwd)`는 현재 디렉토리 경로를 의미합니다. PowerShell에서는 잘 작동하지만, 만약 CMD(명령 프롬프트)에서 오류가 발생하면 `$(pwd)` 대신 `%cd%`를 사용하거나, 전체 절대 경로를 직접 입력해주세요. (예: `-v "D:\BackGround\Dev\Python\New_Python\new_4/chzzk_recorder/config:/app/config"`)

---

## 3단계: 로그 확인

컨테이너가 백그라운드에서 실행 중이므로, `logs` 명령어를 사용하여 프로그램이 어떻게 작동하는지 확인해야 합니다.

**현재까지의 모든 로그 확인:**
```bash
docker logs chzzk_recorder_container
```

**실시간으로 로그 계속 확인:**
```bash
docker logs -f chzzk_recorder_container
```

- `watcher`가 채널을 확인하는 메시지나, 녹화를 시작하는 메시지가 나타나는지 확인합니다.
- 실시간 로그 확인을 중단하려면 `Ctrl + C`를 누릅니다.

---

## 4단계: 테스트 종료 및 정리

테스트가 끝나면 아래 명령어를 사용하여 컨테이너를 중지하고 삭제할 수 있습니다.

**컨테이너 중지:**
```bash
docker stop chzzk_recorder_container
```

**컨테이너 삭제:**
```bash
docker rm chzzk_recorder_container
```
