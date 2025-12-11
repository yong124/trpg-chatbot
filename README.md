# TRPG AI 챗봇

Gemini API를 활용하여 동적으로 스토리를 생성하는 웹 기반 TRPG(Tabletop Role-Playing Game) 챗봇입니다.

## 🌟 주요 기능

-   **동적 스토리 생성:** 플레이어의 행동에 따라 Gemini AI가 실시간으로 다음 스토리를 만들어냅니다.
-   **2d6 판정 시스템:** 2개의 6면체 주사위를 굴려 나온 결과(완전 성공, 대가를 치르는 성공, 실패)에 따라 이야기의 분기가 달라집니다.
-   **캐릭터 시스템:** 근력, 민첩, 지능, 감각, 정신력 5가지 능력치와 HP/SP 자원을 가집니다.
-   **웹 기반 인터페이스:** 웹 브라우저만 있으면 어디서든 게임을 즐길 수 있습니다.

## 🛠️ 기술 스택

-   **백엔드:** Python, Flask, Gunicorn, Google Generative AI (Gemini)
-   **프론트엔드:** HTML, CSS, JavaScript (Vanilla JS)
-   **배포:** Render (Web Service + Static Site)

## 🚀 로컬에서 실행하기

### 1. 백엔드 실행

1.  **API 키 설정:**
    `backend` 폴더 안에 `api_key.env` 파일을 만들고 다음과 같이 Gemini API 키를 입력하세요.
    ```
    GEMINI_API_KEY="여기에_실제_API_키를_입력하세요"
    ```

2.  **가상 환경 및 라이브러리 설치:**
    ```shell
    # backend 폴더로 이동
    cd backend

    # 가상 환경 생성 (최초 1회)
    python -m venv venv

    # 가상 환경 활성화
    # Windows
    .\venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate

    # 필요한 라이브러리 설치
    pip install -r requirements.txt
    ```

3.  **백엔드 서버 실행:**
    ```shell
    flask run --port=5000
    ```
    서버가 `http://localhost:5000` 에서 실행됩니다.

### 2. 프론트엔드 실행

1.  `frontend` 폴더의 `index.html` 파일을 웹 브라우저에서 엽니다.
2.  (선택) Live Server와 같은 VS Code 확장 프로그램을 사용하면 코드가 변경될 때마다 자동으로 새로고침되어 편리합니다.

이제 `http://localhost:5000` 에서 실행 중인 백엔드와 프론트엔드가 연동되어 게임을 테스트할 수 있습니다.

## 🌐 배포하기 (Render.com 기준)

이 프로젝트는 백엔드와 프론트엔드를 별도의 서비스로 배포해야 합니다. 아래는 **무료 티어**를 기준으로 한 가이드입니다.

### 1단계: GitHub에 프로젝트 업로드

Render는 GitHub 리포지토리에서 직접 코드를 가져와 배포합니다. 먼저 이 프로젝트 전체를 GitHub에 업로드해야 합니다.

### 2단계: 백엔드 배포 (Web Service)

1.  Render 대시보드에서 **[New] > [Web Service]**를 선택합니다.
2.  프로젝트의 GitHub 리포지토리를 연결합니다.
3.  아래와 같이 설정합니다.
    -   **Name:** `trpg-chatbot-backend` (원하는 이름으로 설정)
    -   **Root Directory:** `backend`
    -   **Environment:** `Python`
    -   **Region:** 가까운 지역 선택 (예: Singapore)
    -   **Branch:** `main` (또는 주력 브랜치)
    -   **Build Command:** `pip install -r requirements.txt`
    -   **Start Command:** `gunicorn app:app`

4.  **[Advanced]** 섹션을 열어 **[Add Environment Variable]**을 클릭합니다.
    -   **Key:** `GEMINI_API_KEY`
    -   **Value:** "여기에_실제_API_키를_입력하세요"
    -   **Key:** `FLASK_SECRET_KEY`
    -   **Value:** `[Generate]` 버튼을 눌러 랜덤 키 생성

5.  **[Create Web Service]** 버튼을 눌러 배포를 시작합니다.
6.  배포가 완료되면 `https://your-backend-app.onrender.com` 과 같은 주소가 생성됩니다. 이 주소를 복사해두세요.

### 3단계: 프론트엔드 배포 (Static Site)

1.  `frontend/index.html` 파일을 수정하여 `</body>` 태그 바로 위에 다음 스크립트 태그를 추가합니다. **반드시 `your-backend-app.onrender.com` 부분은 2단계에서 복사한 실제 백엔드 주소로 바꿔주세요.**

    ```html
    <script>
      window.BACKEND_API_BASE_URL = "https://your-backend-app.onrender.com";
    </script>
    </body>
    ```
    이 변경 사항을 GitHub에 다시 푸시합니다.

2.  Render 대시보드에서 **[New] > [Static Site]**를 선택합니다.
3.  프로젝트의 GitHub 리포지토리를 다시 연결합니다.
4.  아래와 같이 설정합니다.
    -   **Name:** `trpg-chatbot-frontend` (원하는 이름으로 설정)
    -   **Root Directory:** `frontend`
    -   **Branch:** `main` (또는 주력 브랜치)
    -   **Build Command:** (비워둠)
    -   **Publish Directory:** `frontend` (혹은 Root Directory를 비워두고 Publish Directory를 `frontend`로 설정해도 됩니다)

5.  **[Create Static Site]** 버튼을 눌러 배포를 시작합니다.

### 4단계: 완료!

프론트엔드 배포가 완료되면 생성된 주소(`https://your-frontend-app.onrender.com`)로 접속하여 게임을 플레이할 수 있습니다.

---
**참고:** Render의 무료 웹 서비스는 15분 동안 요청이 없으면 '잠자기' 상태가 됩니다. 이때 첫 요청은 서버가 다시 깨어나는 데 20~30초 정도 소요될 수 있습니다. 정적 사이트는 항상 켜져 있습니다.
