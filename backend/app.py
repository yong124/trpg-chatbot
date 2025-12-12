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
        # 제목에서 '##' 와 앞뒤 공백을 모두 제거
        section_title = lines[0].strip().lstrip('#').strip()
        # --- 추가된 디버깅 로그 ---
        logger.info(f"Cleaned section title: '[{section_title}]'")
        section_content = '\n'.join(lines[1:]).strip()

        if section_title == '시작 설정':
            settings = {}
            import re
            # 수정된 정규식: 굵은 글씨(**)가 있어도 되고 없어도 되도록 변경
            # 포맷: - 키: 값  또는  - **키**: 값
            # (?=\s*-\s*|\Z)는 다음 항목 시작 또는 문자열 끝까지를 값으로 봄
            pattern = re.compile(r'^\s*-\s*(?:\*\*)?(.*?)(?:\*\*)?:\s*(.*?)(?=\s*-\s*|\Z)', re.DOTALL | re.MULTILINE)
            matches = pattern.findall(section_content)
            for key, value in matches: # _는 lookahead 그룹 무시
                settings[key.strip()] = value.strip()
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

def _create_story_summary(player_char, game_log_session):
    """현재 게임 상태를 기반으로 AI를 위한 요약 객체를 생성합니다."""
    
    # 마지막 GM 메시지 추출
    last_gm_message = "게임 시작."
    for msg in reversed(game_log_session):
        if msg.strip().startswith("<strong>GM:"):
            # HTML 태그 제거
            last_gm_message = msg.replace("<strong>GM:</strong>", "").strip()
            break
            
    # 해결되지 않은 위협 추론 (간단한 키워드 기반)
    unresolved_threats = []
    scenario_state_lower = player_char.get('current_scenario_state', '').lower()
    if any(keyword in scenario_state_lower for keyword in ["추적", "위협", "전투", "다가오는"]):
        unresolved_threats.append(player_char.get('current_scenario_state'))

    story_so_far = {
        "current_goal": player_char.get('current_scenario_state', '플레이어의 다음 행동을 기다리는 중'),
        "last_key_event": last_gm_message,
        "unresolved_threats": unresolved_threats if unresolved_threats else ["특별한 위협 없음."],
        "open_questions": ["다가오는 위협의 정체는 무엇인가?", "이 통로는 어디로 이어지는가?"] # 예시
    }
    return story_so_far


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
    # Scene ID 생성: 위치 문자열을 기반으로 간단한 ID를 만듭니다.
    scene_id = ''.join(filter(str.isalnum, start_location)).upper()
    if not scene_id:
        scene_id = "UNKNOWN_SCENE"

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
        'description': char_description, # Add this line
        'scene_id': scene_id # Scene Lock을 위한 ID 추가
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


def _create_story_summary(player_char, game_log_session):
    """현재 게임 상태를 기반으로 AI를 위한 요약 객체를 생성합니다."""
    
    # 마지막 GM 메시지 추출
    last_gm_message = "게임 시작."
    for msg in reversed(game_log_session):
        if msg.strip().startswith("<strong>GM:"):
            # HTML 태그 제거
            last_gm_message = msg.replace("<strong>GM:</strong>", "").strip()
            break
            
    # 해결되지 않은 위협 추론 (간단한 키워드 기반)
    unresolved_threats = []
    scenario_state_lower = player_char.get('current_scenario_state', '').lower()
    if any(keyword in scenario_state_lower for keyword in ["추적", "위협", "전투", "다가오는"]):
        unresolved_threats.append(player_char.get('current_scenario_state'))

    story_so_far = {
        "current_goal": player_char.get('current_scenario_state', '플레이어의 다음 행동을 기다리는 중'),
        "last_key_event": last_gm_message,
        "unresolved_threats": unresolved_threats if unresolved_threats else ["특별한 위협 없음."],
        "open_questions": ["다가오는 위협의 정체는 무엇인가?", "이 통로는 어디로 이어지는가?"] # 예시
    }
    return story_so_far

def _build_action_prompt(player_char, story_summary, player_action):
    # --- 프롬프트에 사용될 값들을 미리 변수로 추출 ---
    player_action_str = player_action
    current_scenario_state_str = player_char.get('current_scenario_state', 'Unknown')
    current_scene_id = player_char.get('scene_id', 'UNKNOWN_SCENE')
    story_summary_json = json.dumps(story_summary, ensure_ascii=False, indent=2)

    return f"""
# [CONTEXT SUMMARY - PRIMARY DIRECTIVE]
# You must base your response on the following structured summary of the current situation. This is your primary source of truth.
{story_summary_json}

# [SCENE LOCK - CRITICAL RULE]
# You are currently in Scene ID: "{current_scene_id}". Do not change the scene unless the player's action directly causes it.

# [NARRATIVE ANCHOR - ABSOLUTE PRIORITY]
# Your immediate task is to respond to the player's very last action based on the context above.
# 1. Player's Last Action: "{player_action_str}"
# 2. Based on the "current_goal" from the summary, decide if this action requires a dice roll.
# All your narrative output for the 'story' field in the JSON response MUST be in Korean.

# --- GM's Judgment Rules ---
# 1. **CRITICAL:** If you set "require_roll" to `true`, your "story" text MUST end with a clear call for a roll. (e.g., "...감각 판정이 필요합니다.")
# 2. The 'roll_stat' must be one of: "strength", "agility", "intelligence", "senses", "willpower".
# 3. If the "current_goal" from the summary is resolved or significantly changed by the action, reflect this in the "new_scenario_state".

```json
{{
    "story": "[ 여기에 다음 상황 묘사나 판정 요구를 작성합니다. ]",
    "require_roll": false,
    "roll_stat": null,
    "hp_change": 0,
    "sp_change": 0,
    "add_inventory": [],
    "remove_inventory": [],
    "new_location": null,
    "new_scenario_state": "[ 여기에 새로운 상황 요약을 작성합니다. ]",
    "new_scene_id": null
}}
```
"""

def _build_roll_prompt(player_char, story_summary, roll_info):
    # --- 프롬프트에 사용될 값들을 미리 변수로 추출 ---
    pending_action_str = roll_info['pending_action']
    roll_outcome = roll_info['outcome']
    story_summary_json = json.dumps(story_summary, ensure_ascii=False, indent=2)

    return f"""
# [CONTEXT SUMMARY - PRIMARY DIRECTIVE]
# You must base your response on the following structured summary of the current situation.
{story_summary_json}

# [ROLL CONTINUITY RULE - ABSOLUTE PRIORITY]
# Your response must be a direct description of the result of the following **specific action**.
# **Action Being Resolved:** "{pending_action_str}"
# **Dice Roll Result:** "{roll_outcome}"
#
# ❌ Do NOT reference past events from the log. ONLY resolve the action above.
# Only describe "how this action ended".
# All your narrative output for the 'story' field in the JSON response MUST be in Korean.

# --- GM's Story Generation Rules ---
# 1. Describe the story in a way that fits the "{roll_outcome}".
# 2. Clearly state how the **Action Being Resolved** led to the "{roll_outcome}".
# 3. After describing the story, ask a question to guide the player's next action.

# --- Detailed Dice Roll Breakdown (for reference only) ---
# Total {roll_info['total']} (Dice 1: {roll_info['dice1']}, Dice 2: {roll_info['dice2']}, Stat: {roll_info['stat_name_ko']}, Modifier: {roll_info['modifier']})

```json
{{
    "story": "[ 여기에 주사위 굴림 결과에 따른 상세한 상황 묘사와 다음 질문을 작성합니다. ]",
    "require_roll": false,
    "roll_stat": null,
    "hp_change": 0,
    "sp_change": 0,
    "add_inventory": [],
    "remove_inventory": [],
    "new_location": null,
    "new_scenario_state": "[ 여기에 새로운 상황 요약을 작성합니다. ]",
    "new_scene_id": null
}}
```
"""

def _handle_action_turn(data, player_char, game_log_session):
    player_action = data.get('player_action', '아무것도 하지 않는다.')
    logger.debug(f"Live AI Mode - Action: {player_action}")
    
    story_summary = _create_story_summary(player_char, game_log_session)
    prompt = _build_action_prompt(player_char, story_summary, player_action)
    
    response = model.generate_content(prompt, safety_settings=safety_settings)
    ai_json = parse_ai_response(response.text)

    # AI 응답에 따라 세션 상태 업데이트
    if ai_json.get('new_location'):
        player_char['location'] = ai_json['new_location']
    if ai_json.get('new_scenario_state'):
        player_char['current_scenario_state'] = ai_json['new_scenario_state']
    if ai_json.get('new_scene_id'):
        player_char['scene_id'] = ai_json['new_scene_id']
    
    player_char = apply_state_changes(player_char, ai_json)
    session['character_data'] = player_char
    
    game_log_session.append(f"플레이어: {player_action}")
    game_log_session.append(f"<strong>GM:</strong> {ai_json['story']}")
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
    
    return jsonify(final_response)

def _handle_roll_turn(data, player_char, game_log_session, pending_action):
    modifier_stat_name = data.get('modifier_stat')
    stat_value = player_char['stats'].get(modifier_stat_name, 0)
    modifier = get_modifier(stat_value)
    
    dice1, dice2 = random.randint(1, 6), random.randint(1, 6)
    total = dice1 + dice2 + modifier
    
    if total >= 10: roll_outcome = "완전한 성공"
    elif total >= 7: roll_outcome = "대가를 치르는 성공"
    else: roll_outcome = "실패"
    
    STAT_MAPPING_KO = {'strength': '근력', 'agility': '민첩', 'intelligence': '지능', 'senses': '감각', 'willpower': '정신력'}
    stat_name_ko = STAT_MAPPING_KO.get(modifier_stat_name, modifier_stat_name)

    roll_info = {
        'pending_action': pending_action, 'outcome': roll_outcome, 'total': total,
        'dice1': dice1, 'dice2': dice2, 'stat_name_ko': stat_name_ko, 'modifier': modifier
    }
    
    story_summary = _create_story_summary(player_char, game_log_session)
    prompt = _build_roll_prompt(player_char, story_summary, roll_info)

    response = model.generate_content(prompt, safety_settings=safety_settings)
    ai_json = parse_ai_response(response.text)

    # AI 응답에 따라 세션 상태 업데이트
    if ai_json.get('new_location'):
        player_char['location'] = ai_json['new_location']
    if ai_json.get('new_scenario_state'):
        player_char['current_scenario_state'] = ai_json['new_scenario_state']
    
    player_char = apply_state_changes(player_char, ai_json)
    session['character_data'] = player_char
    
    roll_summary = f"GM (판정): {stat_name_ko} 판정 (주사위: {dice1}+{dice2}, 수정치: {modifier}, 총합: {total}) 결과 - {roll_outcome}"
    game_log_session.append(roll_summary)
    game_log_session.append(f"<strong>GM:</strong> {ai_json['story']}")
    session['game_log'] = game_log_session
    session['pending_action_for_roll'] = None
    session.modified = True
    
    final_response = { 
        "dice1": dice1, "dice2": dice2, "total": total, "modifier": modifier, "roll_outcome": roll_outcome, 
        "story": f"{roll_summary}\n{ai_json['story']}",
        "character": player_char
    }
    final_response.update({
        'require_roll': ai_json.get('require_roll', False),
        'roll_stat': ai_json.get('roll_stat', None)
    })

    return jsonify(final_response)

@app.route('/game-turn', methods=['POST'])
def handle_game_turn():
    player_char = session.get('character_data', DEFAULT_PLAYER_CHARACTER)
    game_log_session = session.get('game_log', [])
    pending_action_for_roll = session.get('pending_action_for_roll', None)
    data = request.get_json()
    turn_type = data.get('type', 'action')

    logger.debug(f"\n--- Backend Turn Start ---")
    logger.debug(f"Turn type: {turn_type}, Character: {player_char.get('name')}")
    logger.debug(f"Incoming data: {data}")

    if TEST_MODE:
        # 테스트 모드 로직은 간소화를 위해 이 리팩토링에서 제외하고 기존 로직을 유지합니다.
        # 필요하다면 별도로 리팩토링할 수 있습니다.
        pass # 기존 테스트 모드 코드가 여기에 위치한다고 가정

    try:
        if turn_type == 'action':
            return _handle_action_turn(data, player_char, game_log_session)
        elif turn_type == 'roll':
            return _handle_roll_turn(data, player_char, game_log_session, pending_action_for_roll)
    except Exception as e:
        logger.error(f"An error occurred during game turn: {e}", exc_info=True)
        return jsonify({"story": f"GM: 게임 진행 중 심각한 오류가 발생했습니다: {e}", "require_roll": False, "roll_stat": None}), 500

    return jsonify({"error": "Invalid turn type or test mode issue"}), 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)