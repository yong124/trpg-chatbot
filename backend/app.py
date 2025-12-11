from flask import Flask, jsonify, request, session # session 임포트 추가
from flask_cors import CORS
import random
import os
import google.generativeai as genai
import json
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# --- Gemini API 안전 설정 (검열 해제) ---
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# --- 로깅 설정 ---
LOG_FILE = 'debug.log'
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# 파일 핸들러 (로그 파일에 기록)
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1024 * 1024 * 5, backupCount=5, encoding='utf-8') # 5MB, 5개 파일 순환
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# 콘솔 핸들러 (터미널에도 출력 - 개발 중 확인용)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO) # 콘솔에는 INFO 레벨 이상만 (너무 많은 디버그 로그 방지)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# --- 초기 설정 ---
load_dotenv(dotenv_path='api_key.env')

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_SAMESITE='None',
    SESSION_COOKIE_SECURE=True
)
CORS(app, supports_credentials=True, origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000", "https://trpg-game-g4qw.onrender.com"]) # 프론트엔드 개발 서버 주소 명시
# 개발 중에는 모든 출처를 허용하는 것이 편리하지만, 프로덕션에서는 특정 출처만 허용하는 것이 좋습니다.
# CORS(app, supports_credentials=True, origins=["http://localhost:8000", "http://127.0.0.1:8000", "null"]) # 파일 시스템에서 직접 열 때 "null" origin 발생 가능

# !!! 필수 !!! 세션 사용을 위한 SECRET_KEY 설정
# 환경 변수에서 시크릿 키를 로드하고, 없으면 경고와 함께 임시 키를 사용합니다.
app.secret_key = os.getenv('FLASK_SECRET_KEY')
if not app.secret_key:
    logger.warning("경고: FLASK_SECRET_KEY 환경 변수가 설정되지 않았습니다. 임시 키를 사용합니다. 서버 재시작 시 세션이 초기화됩니다.")
    app.secret_key = os.urandom(24) # 개발용 임시 키

# +++ 테스트 모드 플래그 +++
# True로 설정하면 실제 AI를 호출하지 않고 가짜 응답을 반환합니다.
TEST_MODE = False

# --- Gemini API 설정 ---
if not TEST_MODE:
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다. .env 파일을 확인해주세요.")
        raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다. .env 파일을 확인해주세요.")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('models/gemini-2.5-pro')

# --- Lorebook 불러오기 ---
def parse_lorebook(content):
    """Parses the lorebook markdown content into a dictionary."""
    sections = {}
    # H2 (##)를 기준으로 섹션 분리
    parts = content.split('\n## ')
    for part in parts:
        if not part.strip():
            continue
        
        lines = part.strip().splitlines()
        section_title = lines[0].strip()
        section_content = '\n'.join(lines[1:]).strip()

        if section_title == '시작 설정':
            settings = {}
            # 예시: "- **시작 위치:** 신림역 환승 통로"
            import re
            # 키는 ':' 앞의 마지막 단어 블록으로 가정 (예: "시작 위치")
            # 값은 ':' 뒤의 모든 내용
            pattern = re.compile(r'-\s*\*\*(.*?)\*\*:\s*(.*)')
            for line in section_content.splitlines():
                match = pattern.match(line)
                if match:
                    key = match.group(1).strip()
                    value = match.group(2).strip()
                    settings[key] = value
            sections[section_title] = settings
        elif section_title:
            sections[section_title] = section_content
            
    return sections

LOREBOOK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lorebook.md')
LOREBOOK_DATA = {}
try:
    with open(LOREBOOK_PATH, 'r', encoding='utf-8') as f:
        lorebook_content = f.read()
        LOREBOOK_DATA = parse_lorebook(lorebook_content)
        logger.info(f"Lorebook loaded and parsed successfully. Sections: {list(LOREBOOK_DATA.keys())}")
except FileNotFoundError:
    logger.warning(f"{LOREBOOK_PATH} not found. AI will operate without lorebook context.")
except Exception as e:
    logger.error(f"Error parsing lorebook: {e}")

# --- 게임 상태 관리 ---
# 세션에 캐릭터 데이터가 없을 때 사용될 기본 캐릭터 데이터
DEFAULT_PLAYER_CHARACTER = {
    'name': '탐험가',
    'stats': {
        'strength': 1, 'agility': 1, 'intelligence': 1, 'senses': 1, 'willpower': 1
    },
    'inventory': [],
    'hp': 10,
    'maxHp': 10,
    'sp': 5,
    'maxSp': 5
}

def calculate_resources(stats):
    """주어진 능력치를 기반으로 최대 HP와 SP를 계산합니다."""
    strength = stats.get('strength', 1)
    willpower = stats.get('willpower', 1)
    
    max_hp = 8 + (strength * 2)
    max_sp = 3 + (willpower * 2)
    
    return {'max_hp': max_hp, 'max_sp': max_sp}

# --- 수정치 계산 함수 (사용자 피드백 반영) ---
def get_modifier(stat_value):
    if stat_value >= 3: return 1
    elif stat_value >= 2: return 0
    else: return -1 # 1일 때 -1


def parse_ai_response(response_text):
    try:
        json_str_start = response_text.find("```json")
        json_str_end = response_text.rfind("```")
        if json_str_start != -1 and json_str_end != -1:
            json_payload = response_text[json_str_start + len("```json"):json_str_end].strip()
            return json.loads(json_payload)
    except Exception as e:
        logger.error(f"AI 응답 파싱 오류: {e}\n응답 내용: {response_text}")
        return {"story": f"GM: AI 응답 파싱 오류. 응답 내용: {response_text}", "require_roll": False, "roll_stat": None}


def get_mock_response(turn_type, player_action=None, modifier_stat=None, player_char_name='탐험가'):
    if turn_type == 'action':
        if "살펴" in (player_action or "") or "조사" in (player_action or ""):
            return { "story": f"[테스트 모드] {player_char_name}님, 신림역 승강장을 주의 깊게 살펴보려 합니다. 어둠 속에서 무언가를 찾아내려면 '감각' 판정이 필요합니다.", "require_roll": True, "roll_stat": "senses" }
        elif "문" in (player_action or "") and ("열" in (player_action or "") or "부순다" in (player_action or "")):
             return { "story": f"[테스트 모드] {player_char_name}님, 육중한 문을 열려 합니다. 상당한 힘이 필요해 보입니다. '근력' 판정이 필요합니다.", "require_roll": True, "roll_stat": "strength" }
        else:
            return { "story": f"[테스트 모드] '{player_action}' 행동을 합니다. 별다른 일은 일어나지 않았습니다.", "require_roll": False, "roll_stat": None }
    elif turn_type == 'roll':
        return { "story": f"[테스트 모드] {modifier_stat} 판정 결과, {player_char_name}님, 당신은 멋지게 성공했습니다! 문이 열립니다.", "require_roll": False, "roll_stat": None, "hp_change": -2, "add_inventory": ["녹슨 기어"] }


def apply_state_changes(character, changes):
    """AI 응답에 따라 캐릭터의 상태(HP, SP, 인벤토리)를 변경합니다."""
    # HP 변경
    hp_change = changes.get('hp_change', 0)
    if hp_change != 0:
        character['hp'] = max(0, min(character['maxHp'], character['hp'] + hp_change))

    # SP 변경
    sp_change = changes.get('sp_change', 0)
    if sp_change != 0:
        character['sp'] = max(0, min(character['maxSp'], character['sp'] + sp_change))

    # 인벤토리 추가
    items_to_add = changes.get('add_inventory', [])
    if items_to_add:
        character['inventory'].extend(items_to_add)
        # 중복 제거 (선택 사항)
        character['inventory'] = sorted(list(set(character['inventory'])))

    # 인벤토리 제거
    items_to_remove = changes.get('remove_inventory', [])
    if items_to_remove:
        for item in items_to_remove:
            if item in character['inventory']:
                character['inventory'].remove(item)
    
    logger.debug(f"캐릭터 상태 변경 적용됨: {character}")
    return character


@app.route('/create-character', methods=['POST'])
def create_character():
    # 전역 변수 game_log 및 pending_action_for_roll은 session에서 관리되므로 global 선언 필요 없음
    data = request.get_json()
    
    char_name = data.get('name', DEFAULT_PLAYER_CHARACTER['name'])
    char_stats = data.get('stats', DEFAULT_PLAYER_CHARACTER['stats'])
    char_inventory = data.get('inventory', DEFAULT_PLAYER_CHARACTER['inventory'])
    char_description = data.get('description', '') # Add this line

    # 능력치 기반으로 HP/SP 계산
    resources = calculate_resources(char_stats)
    max_hp = resources['max_hp']
    max_sp = resources['max_sp']

    # 로어북에서 시작 설정 가져오기
    start_settings = LOREBOOK_DATA.get('시작 설정', {})
    # --- 디버깅 로그 추가 ---
    logger.info(f"--- /create-character DEBUG ---")
    logger.info(f"전체 LOREBOOK_DATA: {LOREBOOK_DATA}")
    logger.info(f"추출된 start_settings: {start_settings}")
    # --- 디버깅 로그 끝 ---
    start_location = start_settings.get('시작 위치', '알 수 없는 장소')
    start_state = start_settings.get('시작 상황', '알 수 없는 상황')
    start_message = start_settings.get('시작 메시지', f"{char_name}님, 새로운 여정을 시작합니다.")

    # 세션에 캐릭터 데이터 저장
    session['character_data'] = {
        'name': char_name,
        'stats': char_stats,
        'inventory': char_inventory,
        'hp': max_hp, # 계산된 값으로 설정
        'maxHp': max_hp, # 계산된 값으로 설정
        'sp': max_sp,  # 계산된 값으로 설정
        'maxSp': max_sp,  # 계산된 값으로 설정
        'location': start_location,
        'current_scenario_state': start_state,
        'description': char_description # Add this line
    }
    # 게임 상태도 세션에서 관리
    session['game_log'] = [f"<strong>GM:</strong> {start_message}"] # 로어북 기반 시작 메시지
    session['pending_action_for_roll'] = None
    session.modified = True # 세션이 확실히 저장되도록 보장

    logger.info(f"캐릭터 생성됨 (세션): {session['character_data']['name']}, 능력치: {session['character_data']['stats']}, 인벤토리: {session['character_data']['inventory']}, HP: {max_hp}, SP: {max_sp}")
    return jsonify({
        "status": "success", 
        "message": "캐릭터가 성공적으로 생성되었습니다.",
        "character": session['character_data'],
        "initial_message": f"<strong>GM:</strong> {start_message}"
    })


@app.route('/game-turn', methods=['POST'])
def handle_game_turn():
    # 세션에서 캐릭터 데이터 및 게임 상태 로드
    player_char = session.get('character_data', DEFAULT_PLAYER_CHARACTER)
    game_log_session = session.get('game_log', [])
    pending_action_for_roll_session = session.get('pending_action_for_roll', None)

    logger.debug(f"\n--- Backend Turn Start ---")
    logger.debug(f"Current player_char from session: {player_char}")
    logger.debug(f"Incoming raw data: {request.get_data(as_text=True)}")
    data = request.get_json()
    logger.debug(f"Parsed JSON data object: {data}")
    
    turn_type = data.get('type', 'action')
    logger.debug(f"Turn type: {turn_type}")


    # --- 테스트 모드 ---
    if TEST_MODE:
        player_action = data.get('player_action')
        modifier_stat = data.get('modifier_stat')
        if turn_type == 'action':
            ai_json = get_mock_response(turn_type, player_action=player_action, player_char_name=player_char['name'])
            
            player_char = apply_state_changes(player_char, ai_json)
            session['character_data'] = player_char

            game_log_session.append(f"플레이어: {player_action}")
            game_log_session.append(f"GM: {ai_json['story']}")
            session['game_log'] = game_log_session
            session.modified = True

            # 프론트엔드로 보낼 최종 응답 구성
            final_response = ai_json.copy()
            final_response['character'] = player_char
            logger.debug(f"Returning from TEST_MODE (action): {final_response}")
            return jsonify(final_response)
        
        elif turn_type == 'roll':
            modifier_stat = data.get('modifier_stat')
            modifier = get_modifier(player_char['stats'].get(modifier_stat, 0))
            dice1, dice2 = random.randint(1, 6), random.randint(1, 6)
            total = dice1 + dice2 + modifier
            roll_outcome = "테스트 성공"
            ai_json = get_mock_response(turn_type, modifier_stat=modifier_stat, player_char_name=player_char['name'])
            
            player_char = apply_state_changes(player_char, ai_json)
            session['character_data'] = player_char

            roll_summary = f"GM (판정): {modifier_stat} 판정 (주사위: {dice1}+{dice2}, 수정치: {modifier}, 총합: {total}) 결과 - {roll_outcome}"
            
            game_log_session.append(f"플레이어: {pending_action_for_roll_session or '알 수 없는 행동'} 판정을 위해 주사위를 굴립니다.")
            game_log_session.append(roll_summary)
            game_log_session.append(f"GM: {ai_json['story']}")
            session['game_log'] = game_log_session
            session['pending_action_for_roll'] = None
            session.modified = True

            final_response = { 
                "dice1": dice1, "dice2": dice2, "total": total, "modifier": modifier, "roll_outcome": roll_outcome, 
                "story": f"{roll_summary}\n{ai_json['story']}", 
                "require_roll": False, "roll_stat": None,
                "character": player_char
            }
            logger.debug(f"Returning from TEST_MODE (roll): {final_response}")
            return jsonify(final_response)

    # --- 라이브 AI 모드 (TEST_MODE = False) ---
    try:
        if turn_type == 'action':
            player_action = data.get('player_action', '아무것도 하지 않는다.')
            logger.debug(f"Live AI Mode - Action: {player_action}")
            game_log_session.append(f"플레이어: {player_action}")
            
            # 프롬프트에 현재 캐릭터 상태 포함
            prompt = f"""
            당신은 TRPG 게임의 숙련된 게임 마스터(GM)입니다. 아래 '게임 설정'을 숙지하고, 그에 맞춰 스토리를 진행하세요.

            # 게임 설정:
            - 세계관: {LOREBOOK_DATA.get('세계관', '설정되지 않음')}
            - 배경: {LOREBOOK_DATA.get('배경', '설정되지 않음')}
            - 플레이어 캐릭터: {LOREBOOK_DATA.get('플레이어 캐릭터', '설정되지 않음')}
            - 주요 인물 (NPC): {LOREBOOK_DATA.get('주요 인물 (NPC)', '설정되지 않음')}

            # GM 지침:
            {LOREBOOK_DATA.get('GM 지침', '플레이어의 행동에 맞춰 스토리를 진행하세요.')}

            # 현재 게임 상태:
            현재 플레이어 캐릭터의 이름은 '{player_char['name']}'이고, 상태는 다음과 같습니다:
            - 능력치: {player_char['stats']}
            - HP: {player_char['hp']}/{player_char['maxHp']}
            - SP: {player_char['sp']}/{player_char['maxSp']}
                        - 인벤토리: {player_char['inventory']}
                        - 캐릭터 설정: {player_char.get('description', '설정되지 않음')}
                        - 현재 위치: {player_char.get('location', '알 수 없음')}
                        - 현재 상황: {player_char.get('current_scenario_state', '알 수 없음')}
            
                        당신은 플레이어의 행동을 듣고, 게임 규칙에 따라 다음 상황을 묘사하고 필요한 경우 판정을 요구해야 합니다.            절대 주사위를 굴리거나 판정 결과를 예측하지 마십시오. 오직 상황 묘사와 판정 요구만 하십시오.

            # 최근 게임 기록:
            {json.dumps(game_log_session[-20:], ensure_ascii=False)}

            # GM의 판단 규칙:
            1.  플레이어의 행동이 명확하고 즉각적인 결과가 나온다면(예: 가만히 있는다, 대화한다), 주사위 굴림 없이 결과를 상세히 묘사하고 다음 행동을 유도하세요.
            2.  플레이어의 행동이 위험하거나 성공 여부가 불확실하다면, 가장 적절한 능력치(strength, agility, intelligence, senses, willpower 중 하나)를 선택하여 주사위 굴림을 요구하세요.
                -   예시: "이것을 시도하려면 [능력치] 판정이 필요합니다."
            3.  스토리 묘사에 따라 플레이어의 상태(HP, SP, 인벤토리)에 변화가 생긴다면, 반드시 JSON의 `hp_change`, `sp_change`, `add_inventory`, `remove_inventory` 필드를 사용하여 그 변화를 표현해야 합니다.
            4.  응답은 반드시 아래 JSON 형식의 마크다운 코드 블록으로만 제공해야 합니다. 다른 어떠한 설명이나 추가 텍스트도 포함하지 마십시오.
            5.  'roll_stat'은 반드시 "strength", "agility", "intelligence", "senses", "willpower" 중 **영어 이름** 하나여야 합니다.
            6.  플레이어가 장소를 이동하여 위치가 확실히 바뀌었다면, 반드시 JSON의 "new_location" 필드에 새로운 장소 이름을 명확히 적으세요. 바뀌지 않았다면 null로 두세요. 이동 중 특별한 사건이 없다면, 다음 목적지에 도착하는 과정을 묘사하고 다음 행동을 유도하세요.
            7.  현재 게임의 전반적인 상황이나 분위기(예: 전투 발생, 위협 제거, 중요한 단서 발견 등)가 크게 변했다면, 반드시 JSON의 "new_scenario_state" 필드에 현재 상황을 한 문장으로 요약해서 적으세요. 바뀌지 않았다면 null로 두세요.
            8.  플레이어가 이동을 선언했다면 (예: '어디로 향한다', '이곳을 떠난다'), 새로운 지역으로의 이동 과정을 상세하게 묘사하고, 새로운 지역에 도착했을 때의 상황을 설명하며 다음 행동을 유도하세요. 불필요하게 전투를 유발하지 마세요.

            ```json
            {{
                "story": "여기에 GM의 다음 상황 묘사나 판정 요구를 상세히 작성합니다.",
                "require_roll": true 또는 false,
                "roll_stat": "주사위 굴림이 필요하다면 여기에 필요한 능력치(예: 'strength')를 작성합니다. 필요 없다면 null",
                "hp_change": 0,
                "sp_change": 0,
                "add_inventory": [],
                "remove_inventory": [],
                "new_location": "플레이어가 이동한 경우 새 장소 이름 (예: '무너진 백화점 1층 로비'), 아니면 null",
                "new_scenario_state": "현재 게임의 상황을 한 문장으로 요약 (예: '플레이어는 포식자와 전투 중'), 아니면 null"
            }}
            ```
            """
            response = model.generate_content(prompt, safety_settings=safety_settings)
            ai_json = parse_ai_response(response.text)

            # [추가] 위치 업데이트 로직
            if ai_json.get('new_location'):
                player_char['location'] = ai_json['new_location']
                logger.info(f"위치 변경됨: {player_char['location']}")

            # [추가] 시나리오 상태 업데이트 로직
            if ai_json.get('new_scenario_state'):
                player_char['current_scenario_state'] = ai_json['new_scenario_state']
                logger.info(f"시나리오 상태 변경됨: {player_char['current_scenario_state']}")

            # AI 응답에 따른 캐릭터 상태 변경
            player_char = apply_state_changes(player_char, ai_json)
            session['character_data'] = player_char
            
            game_log_session.append(f"GM: {ai_json['story']}")
            if ai_json.get('require_roll'):
                session['pending_action_for_roll'] = player_action
            
            session['game_log'] = game_log_session
            session.modified = True
            
            # 프론트엔드로 보낼 최종 응답 구성
            final_response = ai_json.copy()
            final_response['character'] = player_char
            if final_response.get('require_roll') and final_response.get('roll_stat'):
                STAT_MAPPING_KO = {'strength': '근력', 'agility': '민첩', 'intelligence': '지능', 'senses': '감각', 'willpower': '정신력'}
                final_response['roll_stat_ko'] = STAT_MAPPING_KO.get(final_response['roll_stat'], final_response['roll_stat'])
            logger.debug(f"Live AI Mode - Action Response: {final_response}")
            return jsonify(final_response)

        elif turn_type == 'roll':
            modifier_stat_name = data.get('modifier_stat')
            logger.debug(f"Live AI Mode - Roll: modifier_stat_name received: {modifier_stat_name}")
            
            stat_value = player_char['stats'].get(modifier_stat_name, 0)
            modifier = get_modifier(stat_value)
            
            dice1, dice2 = random.randint(1, 6), random.randint(1, 6)
            total = dice1 + dice2 + modifier
            if total >= 10: roll_outcome = "완전한 성공"
            elif total >= 7: roll_outcome = "대가를 치르는 성공"
            else: roll_outcome = "실패"
            
            STAT_MAPPING_KO = {'strength': '근력', 'agility': '민첩', 'intelligence': '지능', 'senses': '감각', 'willpower': '정신력'}
            stat_name_ko = STAT_MAPPING_KO.get(modifier_stat_name, modifier_stat_name)

            prompt = f"""
            당신은 TRPG 게임의 숙련된 게임 마스터(GM)입니다. 아래 '게임 설정'을 숙지하고, 그에 맞춰 스토리를 진행하세요.

            # 게임 설정:
            - 세계관: {LOREBOOK_DATA.get('세계관', '설정되지 않음')}
            - 배경: {LOREBOOK_DATA.get('배경', '설정되지 않음')}
            - 플레이어 캐릭터: {LOREBOOK_DATA.get('플레이어 캐릭터', '설정되지 않음')}
            - 주요 인물 (NPC): {LOREBOOK_DATA.get('주요 인물 (NPC)', '설정되지 않음')}

            # GM 지침:
            {LOREBOOK_DATA.get('GM 지침', '플레이어의 행동에 맞춰 스토리를 진행하세요.')}

            # 현재 게임 상태:
            현재 플레이어 캐릭터의 이름은 '{player_char['name']}'이고, 상태는 다음과 같습니다:
            - 능력치: {player_char['stats']}
            - HP: {player_char['hp']}/{player_char['maxHp']}
            - SP: {player_char['sp']}/{player_char['maxSp']}
            - 인벤토리: {player_char['inventory']}
            - 캐릭터 설정: {player_char.get('description', '설정되지 않음')}
            - 현재 위치: {player_char.get('location', '알 수 없음')}
            - 현재 상황: {player_char.get('current_scenario_state', '알 수 없음')}

            당신은 플레이어의 이전 행동 선언과 주사위 굴림 결과를 바탕으로 다음 스토리를 생성해야 합니다.
            절대 주사위를 굴리거나 판정 요구를 하지 마십시오. 오직 결과에 따른 스토리 묘사만 하십시오.

            # 최근 게임 기록:
            {json.dumps(game_log_session[-20:], ensure_ascii=False)}

            # 플레이어가 시도한 행동: "{pending_action_for_roll_session or '알 수 없는 행동'}"
            # 주사위 굴림 결과: 총합 {total} (첫 번째 주사위: {dice1}, 두 번째 주사위: {dice2}, 적용된 능력치: {stat_name_ko}, 기본 능력치: {stat_value}, 수정치: {modifier} 포함)
            # 최종 판정: {roll_outcome}

            # GM의 스토리 생성 규칙:
            1.  '{roll_outcome}' 결과에 걸맞는 흥미진진하고 구체적인 스토리를 묘사해주세요.
            2.  플레이어의 이전 행동과 주사위 굴림 결과가 스토리 전개에 자연스럽게 녹아들도록 하세요.
            3.  스토리 묘사에 따라 플레이어의 상태(HP, SP, 인벤토리)에 변화가 생긴다면, 반드시 JSON의 `hp_change`, `sp_change`, `add_inventory`, `remove_inventory` 필드를 사용하여 그 변화를 표현해야 합니다.
            4.  스토리 묘사 후, 플레이어가 다음에 무엇을 할지 궁금해지도록 자연스럽게 다음 행동이나 선택지를 유도하는 질문을 던져주세요.
            5.  응답은 반드시 아래 JSON 형식의 마크다운 코드 블록으로만 제공해야 합니다. 다른 어떠한 설명이나 추가 텍스트도 포함하지 마십시오.
            6.  현재 게임의 전반적인 상황이나 분위기가 크게 변했다면, JSON의 "new_scenario_state" 필드에 현재 상황을 한 문장으로 요약해서 적으세요. 바뀌지 않았다면 null로 두세요.

            ```json
            {{
                "story": "여기에 주사위 굴림 결과에 따른 상세한 상황 묘사와 다음 질문을 작성합니다.",
                "require_roll": false,
                "roll_stat": null,
                "hp_change": 0,
                "sp_change": 0,
                "add_inventory": [],
                "remove_inventory": [],
                "new_location": null,
                "new_scenario_state": "현재 게임의 상황을 한 문장으로 요약 (예: '포식자가 쓰러지고 플레이어가 주변을 조사 중'), 아니면 null"
            }}
            ```
            """
            response = model.generate_content(prompt, safety_settings=safety_settings)
            ai_json = parse_ai_response(response.text)

            # [추가] 위치 업데이트 로직
            if ai_json.get('new_location'):
                player_char['location'] = ai_json['new_location']
                logger.info(f"위치 변경됨: {player_char['location']}")

            # [추가] 시나리오 상태 업데이트 로직
            if ai_json.get('new_scenario_state'):
                player_char['current_scenario_state'] = ai_json['new_scenario_state']
                logger.info(f"시나리오 상태 변경됨: {player_char['current_scenario_state']}")

            # AI 응답에 따른 캐릭터 상태 변경
            player_char = apply_state_changes(player_char, ai_json)
            session['character_data'] = player_char
            
            roll_summary = f"GM (판정): {stat_name_ko} 판정 (주사위: {dice1}+{dice2}, 수정치: {modifier}, 총합: {total}) 결과 - {roll_outcome}"
            game_log_session.append(roll_summary)
            game_log_session.append(f"GM: {ai_json['story']}")
            session['game_log'] = game_log_session
            session['pending_action_for_roll'] = None
            session.modified = True
            
            final_response = { 
                "dice1": dice1, "dice2": dice2, "total": total, "modifier": modifier, "roll_outcome": roll_outcome, 
                "story": f"{roll_summary}\n{ai_json['story']}",
                "character": player_char
            }
            # ai_json에서 'require_roll'과 'roll_stat'을 가져와 final_response에 추가
            final_response.update({
                'require_roll': ai_json.get('require_roll', False),
                'roll_stat': ai_json.get('roll_stat', None)
            })

            logger.debug(f"Live AI Mode - Roll Response: {final_response}")
            return jsonify(final_response)
    except Exception as e:
        logger.error(f"AI 호출 중 오류 발생: {e}")
        return jsonify({"story": f"GM: AI 호출 중 심각한 오류가 발생했습니다: {e}", "require_roll": True, "roll_stat": "senses"}), 500

    return jsonify({"error": "Invalid turn type"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)