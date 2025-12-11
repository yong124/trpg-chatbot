# TRPG AI 챗봇 배포 과정 및 문제 해결 요약

이 문서는 TRPG AI 챗봇 프로젝트를 로컬 개발 환경에서 웹에 성공적으로 배포하고, 이후 발생한 버그들을 해결한 전체 과정을 기록합니다.

## 1. 초기 배포 목표

-   **애플리케이션:** Flask 백엔드와 순수 JavaScript 프론트엔드로 구성된 TRPG 챗봇.
-   **배포 플랫폼:** Render.com
-   **전략:** 백엔드는 'Web Service'로, 프론트엔드는 'Static Site'로 분리하여 배포.

## 2. 배포 준비 단계

-   **백엔드 준비:** 운영 환경에서 안정적인 실행을 위해 `gunicorn`을 `requirements.txt`에 추가.
-   **프론트엔드 준비:** 로컬 주소(`localhost`)로 고정된 API 호출 주소를, 배포 시 유연하게 변경할 수 있도록 `window.BACKEND_API_BASE_URL` 변수를 사용하도록 `script.js` 수정.

## 3. GitHub 업로드 과정

-   **문제 발생:** GitHub 웹사이트에서 폴더 직접 업로드가 불가능한 문제 발생.
-   **해결:** **GitHub Desktop** 프로그램을 사용하여 로컬의 프로젝트 폴더 전체를 GitHub 저장소에 업로드(Push)하는 것으로 해결.
-   **보안 조치:** 사용자의 API 키가 포함된 `api_key.env` 파일이 GitHub에 올라가지 않도록, 프로젝트 루트에 `.gitignore` 파일을 생성하여 해당 파일을 명시적으로 제외함.

## 4. 백엔드 배포 (Render Web Service)

백엔드 배포 과정에서 여러 번의 배포 실패를 겪었으며, 원인과 해결 과정은 다음과 같다.

### 4.1. 1차 실패: `ModuleNotFoundError`
-   **원인:** `requirements.txt` 파일에 `google-generativeai`와 `python-dotenv` 라이브러리가 누락되어, 서버가 실행에 필요한 모듈을 찾지 못함.
-   **해결:** `requirements.txt`에 누락된 두 라이브러리를 추가하고 재배포.

### 4.2. 2차 실패: `FileNotFoundError`
-   **원인:** `app.py` 코드 내에 `debug.log`, `lorebook.md` 등의 파일 경로가 `backend/` 접두사를 포함하고 있었음. Render는 실행 기준 디렉토리를 `backend`로 설정했기 때문에, `backend/backend/debug.log` 와 같은 잘못된 경로를 찾으려 시도함.
-   **해결:** `app.py` 내의 모든 파일 경로에서 불필요한 `backend/` 접두사를 제거하고 재배포.

**-> 위 문제 해결 후 백엔드 배포 성공.**

## 5. 프론트엔드 배포 (Render Static Site)

-   **백엔드 연결:** 성공적으로 배포된 백엔드 URL(`https://trpg-chatbot.onrender.com`)을 `frontend/index.html` 파일에 `<script>` 태그로 삽입하여 `window.BACKEND_API_BASE_URL` 변수에 할당.
-   **Render 설정:** `Root Directory`를 비워두고 `Publish Directory`를 `frontend`로 설정하여 경로 문제 해결.

**-> 프론트엔드 배포 성공.**

## 6. 배포 후 버그 수정

### 6.1. 레이아웃 버그: 사이드바 너비 축소
-   **증상:** 채팅창에 긴 내용이 입력되면 왼쪽 사이드바의 너비가 쪼그라드는 현상.
-   **원인 분석:**
    1.  초기에는 `style.css` 파일을 수정했으나, 실제 스타일은 `index.html` 내의 `<style>` 태그에 있었음을 뒤늦게 파악함 (핵심 실수).
    2.  Flexbox 레이아웃에서, 내용이 길어진 자식 요소(`chat-area`)가 부모가 허용한 공간 이상으로 확장하려 하면서, 옆에 있던 다른 자식 요소(`sidebar`)를 강제로 축소시키는 문제.
-   **해결:** `index.html` 파일 내부의 `<style>` 태그를 직접 수정.
    1.  `#sidebar`에 `flex-shrink: 0;` 속성을 추가하여 너비가 줄어들지 않도록 강제.
    2.  `#chat-area`에 `min-width: 0;` 속성을 추가하여 내용물이 부모를 넘어서는 것을 방지.

### 6.2. 데이터 버그: 캐릭터 정보 초기화
-   **증상:** 배포된 사이트에서 캐릭터 생성 후 첫 채팅을 입력하면, 캐릭터 정보가 기본값(능력치 1,1,1,1,1)으로 초기화됨.
-   **원인:** 프론트엔드와 백엔드의 도메인이 달라, 브라우저의 `SameSite` 쿠키 보안 정책에 의해 세션 쿠키 전송이 차단됨. 이로 인해 백엔드가 사용자를 식별하지 못하고 기본 캐릭터 정보를 반환함.
-   **해결:** `app.py`에 Flask 앱 설정을 추가하여, 세션 쿠키가 다른 도메인 간에도 안전하게 전송될 수 있도록 `SESSION_COOKIE_SAMESITE='None'`와 `SESSION_COOKIE_SECURE=True` 옵션을 설정함.

---
*이 문서는 향후 유지보수를 위해 작성되었습니다.*
