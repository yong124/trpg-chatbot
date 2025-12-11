document.addEventListener('DOMContentLoaded', () => {
    // --- API 설정 ---
    const API_BASE_URL = window.BACKEND_API_BASE_URL || 'http://localhost:5000'; // 배포 시 실제 백엔드 주소로 변경될 수 있음

    // --- DOM 요소 가져오기 ---
    const chatLog = document.getElementById('log');
    const playerActionInput = document.getElementById('player-action-input');
    const sendActionBtn = document.getElementById('send-action-btn');
    const diceRollArea = document.getElementById('dice-roll-area');
    const diceDisplay = document.getElementById('dice-display');
    const rollDiceBtn = document.getElementById('roll-dice-btn');

    // 캐릭터 생성 관련 DOM 요소
    const charCreationScreen = document.getElementById('character-creation-screen');
    const gameContainer = document.getElementById('game-container');
    const charNameInput = document.getElementById('char-name');
    const statAllocationDiv = document.getElementById('stat-allocation');
    const remainingPointsSpan = document.getElementById('remaining-points');
    const initialInventoryTextarea = document.getElementById('initial-inventory');
    const createCharacterBtn = document.getElementById('create-character-btn');

    // 캐릭터 정보 표시 DOM 요소
    const displayCharName = document.getElementById('display-char-name');
    const displayLocation = document.getElementById('display-location');
    const displayScenarioState = document.getElementById('display-scenario-state');
    const displayStrength = document.getElementById('display-strength');
    const displayAgility = document.getElementById('display-agility');
    const displayIntelligence = document.getElementById('display-intelligence');
    const displaySenses = document.getElementById('display-senses');
    const displayWillpower = document.getElementById('display-willpower');
    const playerHpSpan = document.getElementById('player-hp');
    const playerMaxHpSpan = document.getElementById('player-max-hp');
    const playerSpSpan = document.getElementById('player-sp');
    const playerMaxSpSpan = document.getElementById('player-max-sp');
    // 추가된 상태 바 DOM 요소
    const playerHpBar = document.getElementById('player-hp-bar');
    const playerSpBar = document.getElementById('player-sp-bar');

    // --- 게임 상태 변수 ---
    let animationInterval;
    let pendingRollStat = null; // AI가 요구한 주사위 굴림 능력치(영어)를 저장
    let pendingRollStatKo = null; // AI가 요구한 주사위 굴림 능력치(한글)를 저장

    // 플레이어 캐릭터 데이터 (초기값 및 생성 후 사용)
    let playerCharacter = {}; // 백엔드에서 데이터를 받아 채울 것이므로 빈 객체로 시작

    // --- 유틸리티 함수 ---
    function addMessageToLog(message, type = 'gm-message') {
        const p = document.createElement('p');
        p.classList.add(type);
        p.innerHTML = message;
        chatLog.appendChild(p);
        chatLog.scrollTop = chatLog.scrollHeight;
    }

    function setDiceRollAreaState(enabled, stat = '', statKo = '') {
        pendingRollStat = enabled ? stat : null;
        pendingRollStatKo = enabled ? statKo : null; // 한글 스탯 이름도 함께 관리
        if (enabled) {
            diceRollArea.classList.remove('disabled');
            rollDiceBtn.removeAttribute('disabled');
            // 한글 스탯 이름이 있으면 사용하고, 없으면 영어 스탯 이름을 사용
            const displayStat = statKo || stat; 
            rollDiceBtn.textContent = displayStat ? `${displayStat} 판정 (2d6)` : '주사위 굴리기 (2d6)';
        } else {
            diceRollArea.classList.add('disabled');
            rollDiceBtn.setAttribute('disabled', 'true');
            rollDiceBtn.textContent = '주사위 굴리기 (2d6)';
        }
    }

    function startDiceAnimation() {
        animationInterval = setInterval(() => {
            const r1 = Math.floor(Math.random() * 6) + 1;
            const r2 = Math.floor(Math.random() * 6) + 1;
            diceDisplay.textContent = `${r1} + ${r2}`;
        }, 100);
    }

    function stopDiceAnimation() {
        clearInterval(animationInterval);
    }

    // 캐릭터 UI를 업데이트하는 함수
    function updateCharacterUI(characterData) {
        playerCharacter = characterData; // 전역 변수 업데이트

        displayCharName.textContent = playerCharacter.name;
        displayLocation.textContent = playerCharacter.location || '알 수 없음';
        displayScenarioState.textContent = playerCharacter.current_scenario_state || '알 수 없음';
        displayStrength.textContent = playerCharacter.stats.strength;
        displayAgility.textContent = playerCharacter.stats.agility;
        displayIntelligence.textContent = playerCharacter.stats.intelligence;
        displaySenses.textContent = playerCharacter.stats.senses;
        displayWillpower.textContent = playerCharacter.stats.willpower;
        
        // HP/SP 값 업데이트
        playerHpSpan.textContent = playerCharacter.hp;
        playerMaxHpSpan.textContent = playerCharacter.maxHp;
        playerSpSpan.textContent = playerCharacter.sp;
        playerMaxSpSpan.textContent = playerCharacter.maxSp;
        
        // HP/SP 바 업데이트
        const hpPercent = (playerCharacter.hp / playerCharacter.maxHp) * 100;
        const spPercent = (playerCharacter.sp / playerCharacter.maxSp) * 100;
        playerHpBar.style.width = `${hpPercent}%`;
        playerSpBar.style.width = `${spPercent}%`;
        
        // 인벤토리 목록 업데이트
        const invList = document.getElementById('inventory-list');
        invList.innerHTML = ''; // 기존 목록 초기화
        playerCharacter.inventory.forEach(item => {
            const li = document.createElement('li');
            li.textContent = item;
            invList.appendChild(li);
        });
    }

    function setActionInputState(enabled, message) {
        playerActionInput.disabled = !enabled;
        sendActionBtn.disabled = !enabled;
        if (message) {
            playerActionInput.placeholder = message;
        }
    }

    // --- 캐릭터 생성 UI 로직 ---
    const TOTAL_STAT_POINTS = 8;
    const MIN_STAT = 1;
    const MAX_STAT = 3;

    let allocatedStats = {
        strength: 1, agility: 1, intelligence: 1, senses: 1, willpower: 1
    };

    function calculateRemainingPoints() {
        let sum = Object.values(allocatedStats).reduce((acc, val) => acc + val, 0);
        return TOTAL_STAT_POINTS - sum;
    }

    function updateStatsAllocationDisplay() {
        for (const stat in allocatedStats) {
            document.getElementById(`alloc-${stat}`).textContent = allocatedStats[stat];
        }
        const remaining = calculateRemainingPoints();
        remainingPointsSpan.textContent = remaining;

        // 버튼 활성화/비활성화 로직
        document.querySelectorAll('.stat-btn.minus').forEach(button => {
            const statName = button.dataset.stat;
            button.disabled = allocatedStats[statName] <= MIN_STAT;
        });
        document.querySelectorAll('.stat-btn.plus').forEach(button => {
            const statName = button.dataset.stat;
            button.disabled = allocatedStats[statName] >= MAX_STAT || remaining <= 0;
        });

        // 생성 버튼 활성화/비활성화 (모든 포인트 분배 및 이름 입력 확인)
        createCharacterBtn.disabled = remaining !== 0 || !charNameInput.value.trim();
    }

    statAllocationDiv.addEventListener('click', (event) => {
        const button = event.target;
        if (button.classList.contains('stat-btn')) {
            const statName = button.dataset.stat;
            if (button.classList.contains('minus')) {
                if (allocatedStats[statName] > MIN_STAT) {
                    allocatedStats[statName]--;
                }
            } else if (button.classList.contains('plus')) {
                if (allocatedStats[statName] < MAX_STAT && calculateRemainingPoints() > 0) {
                    allocatedStats[statName]++;
                }
            }
            updateStatsAllocationDisplay();
        }
    });
    charNameInput.addEventListener('input', updateStatsAllocationDisplay); // 이름 입력 시에도 버튼 상태 업데이트

    // 초기 능력치 UI 설정
    updateStatsAllocationDisplay();

    createCharacterBtn.addEventListener('click', async () => {
        const name = charNameInput.value.trim();
        if (!name) {
            alert("캐릭터 이름을 입력해주세요!");
            return;
        }
        if (calculateRemainingPoints() !== 0) {
            alert("남은 능력치 점수를 모두 분배해주세요!");
            return;
        }

        // 프론트엔드에서 보낼 캐릭터 데이터 구조화
        const characterDataToSend = {
            name: name,
            stats: { ...allocatedStats },
            inventory: initialInventoryTextarea.value.split(',').map(item => item.trim()).filter(item => item)
        };

        // 백엔드로 캐릭터 데이터 전송
        try {
            const response = await fetch(`${API_BASE_URL}/create-character`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include', 
                body: JSON.stringify(characterDataToSend)
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(`캐릭터 생성 오류: ${errorData.message || response.statusText}`);
            }

            const result = await response.json();
            console.log("캐릭터 생성 백엔드 응답:", result);

            if (result.status === 'success' && result.character) {
                // 백엔드에서 받은 최종 데이터로 UI 업데이트
                updateCharacterUI(result.character);

                // UI 전환
                charCreationScreen.classList.add('hidden');
                gameContainer.classList.remove('hidden');
                document.querySelector('.tab-button.active').click(); // 캐릭터 탭 활성화

                // 게임 시작 메시지 (백엔드에서 받은 동적 메시지 사용)
                if (result.initial_message) {
                    addMessageToLog(result.initial_message);
                }
            } else {
                throw new Error('백엔드에서 캐릭터 데이터를 받지 못했습니다.');
            }

        } catch (error) {
            console.error('백엔드로 캐릭터 데이터 전송 중 오류 발생:', error);
            addMessageToLog(`<strong>GM:</strong> 캐릭터 데이터를 백엔드로 전송하는 데 실패했습니다: ${error.message}.`, 'gm-message');
        }
    });


    // --- 핵심 게임 로직 함수 ---
    async function handleAction() {
        const actionText = playerActionInput.value.trim();
        if (!actionText || playerActionInput.disabled) return;

        addMessageToLog(`<strong>플레이어:</strong> ${actionText}`, 'player-message');
        playerActionInput.value = '';
        setDiceRollAreaState(false);
        setActionInputState(false, 'GM이 응답을 준비하고 있습니다...');

        try {
            const response = await fetch(`${API_BASE_URL}/game-turn`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ type: 'action', player_action: actionText })
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const data = await response.json();
            addMessageToLog(`<strong>GM:</strong> ${data.story}`);

            // 서버로부터 받은 최신 캐릭터 정보로 UI 업데이트
            if (data.character) {
                updateCharacterUI(data.character);
            }

            if (data.require_roll && data.roll_stat) {
                setDiceRollAreaState(true, data.roll_stat, data.roll_stat_ko);
            }

        } catch (error) {
            console.error('Action Error:', error);
            addMessageToLog(`<strong>GM:</strong> 오류가 발생했습니다: ${error.message}. 다시 시도해주세요.`, 'gm-message');
        } finally {
            // 주사위 굴림이 필요하지 않은 경우에만 입력창을 다시 활성화
            if (!pendingRollStat) {
                setActionInputState(true, '여기에 행동을 입력하세요 (예: 승강장을 둘러본다)...');
            }
        }
    }

    async function handleRoll() {
        const statToRoll = pendingRollStat;
        if (!statToRoll) {
            console.error("버그: 굴려야 할 능력치(statToRoll)가 설정되지 않았습니다.");
            return;
        }
        
        const displayStat = pendingRollStatKo || statToRoll;
        addMessageToLog(`<strong>플레이어:</strong> ${displayStat} 판정을 위해 주사위를 굴립니다...`, 'player-message');
        setDiceRollAreaState(false);
        startDiceAnimation();

        try {
            const response = await fetch(`${API_BASE_URL}/game-turn`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ type: 'roll', modifier_stat: statToRoll })
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

            const data = await response.json();
            stopDiceAnimation();
            diceDisplay.textContent = `${data.dice1} + ${data.dice2}`;
            addMessageToLog(`<strong>GM:</strong> ${data.story}`);

            // 서버로부터 받은 최신 캐릭터 정보로 UI 업데이트
            if (data.character) {
                updateCharacterUI(data.character);
            }
            
            // 굴림 후에는 항상 행동 입력을 활성화
            setActionInputState(true, '여기에 행동을 입력하세요 (예: 승강장을 둘러본다)...');
            
            // 굴림 후에 또 다른 굴림이 필요한 경우가 있다면 상태를 다시 설정 (AI의 "story" 응답에 따라 결정됨)
            if (data.require_roll && data.roll_stat) {
                 setDiceRollAreaState(true, data.roll_stat, data.roll_stat_ko);
            }

        } catch (error) {
            console.error('Roll Error:', error);
            addMessageToLog(`<strong>GM:</strong> 오류가 발생했습니다: ${error.message}.`, 'gm-message');
            stopDiceAnimation();
            diceDisplay.textContent = '? + ?';
            setDiceRollAreaState(true, statToRoll, pendingRollStatKo); // 오류 시 다시 굴릴 기회 제공
        }
    }


    // --- 이벤트 리스너 설정 ---
    sendActionBtn.addEventListener('click', handleAction);
    playerActionInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleAction();
    });
    rollDiceBtn.addEventListener('click', handleRoll);

    // --- 게임 시작 ---
    // 초기 상태 설정: 캐릭터 생성 화면 표시
    charCreationScreen.classList.remove('hidden');
    gameContainer.classList.add('hidden');
    updateStatsAllocationDisplay();
});