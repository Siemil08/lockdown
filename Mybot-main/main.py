import pymysql
from flask import Flask, request
from auth import find_auth_by_field, find_auth_by_id_code, find_auth_by_user_id, update_user_auth, require_auth
from investigate import investigate_tree_logic
from settlement import calculate_auto_settlement, check_coin_balance
from utils2 import get_conn, create_response, log_all, get_user_status, get_survey_type_by_day, extract_bracket_content, is_long_time_no_see
from datetime import datetime
import pytz

# KST 설정
KST = pytz.timezone('Asia/Seoul')
bypass_users = {}  # user_id: 입력한 키 저장
current_key = None  # 현재 강제입장 키
original_survey_type = None  # 원래 survey_type 저장

# 진입 키 설정
def load_key(filepath='key.txt'):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print("[경고] key.txt 파일이 없습니다.")
        return None

app = Flask(__name__)

@app.route('/skill', methods=['POST'])
def skill():
    global current_key, original_survey_type  # 원래 survey_type을 global로 관리
    conn = None
    try:
        data = request.json
        user_request = data.get('userRequest', {})
        user_id = user_request.get('user', {}).get('id', '')
        user_input = user_request.get('utterance', '').strip()

        # 입장 키 불러오기 
        force_key = load_key()

        # 카카오톡 자동 인증
        user_info = find_auth_by_field('userId', user_id)    

        if not user_info or user_input.isdigit():
            auth_row = find_auth_by_id_code(user_input)
            if auth_row:
                name = auth_row.get('name', '사용자')
                id_code = user_input
                update_user_auth(user_id, id_code)
                msg = f"{name}님 인증 완료!\n무엇을 진행하시겠습니까?\n\n▶ 조사"
                log_all(user_id, id_code, name, "[인증-자동]", "auth", "", msg)
                return create_response(msg)
            elif not user_info:
                return require_auth(user_id)

        # 인증 완료된 사용자 정보
        id_code = user_info['id_code']
        name = user_info['name']
        status = get_user_status(user_id)
        type_ = status['type']
        select_path = status['select_path']
        survey_type = get_survey_type_by_day()
        
        # 디버그: survey_type 출력
        print(f"DEBUG: survey_type={survey_type}")
        
        # 오래된 인증 시간 재갱신
        if is_long_time_no_see(user_info.get('auth_time', '')):
            update_user_auth(user_id, id_code)

        # "테스트" 입력 시 입장 키를 입력받고, 키값이 맞으면 비일상조사로 설정
        if user_input == "테스트":
            msg = "입장 키를 입력해 주세요."
            log_all(user_id, id_code, name, "[테스트-입장]", "test", "", msg)
            return create_response(msg)

        # 키 입력받고 검증
        if user_id in bypass_users and bypass_users[user_id] == force_key:
            # 디버그 메시지: bypass_users 상태와 force_key 출력
            print(f"DEBUG: [키 검증] user_input={user_input}, user_id={user_id}, bypass_users={bypass_users}, force_key={force_key}")
            
            original_survey_type = survey_type  # 비일상조사 시작 전, 원래 survey_type을 저장
            survey_type = "비일상조사"  # 키가 맞으면 비일상조사로 설정
            
            # 디버그 메시지: survey_type 변경 확인
            print(f"DEBUG: [survey_type 변경] original_survey_type={original_survey_type}, survey_type={survey_type}")
            
            msg = "비일상조사 테스트에 진입합니다. 조사를 입력하여 테스트를 진행해 주세요."
            
            # 조사에 진입한 후에는 bypass_users에서 삭제하여 반복되지 않게 처리
            del bypass_users[user_id]  # 키 사용 후 삭제
            
            # 디버그 메시지: bypass_users에서 삭제 확인
            print(f"DEBUG: [bypass_users 삭제] user_id={user_id}, bypass_users={bypass_users}")
        
            log_all(user_id, id_code, name, "[테스트-입장-성공]", "test", "", msg)
            return create_response(msg)

        if user_input == force_key:
            print(f"DEBUG: [입력 키 검증] user_input={user_input}, force_key={force_key}")
            
            bypass_users[user_id] = force_key
            print(f"DEBUG: [bypass_users 추가] user_id={user_id}, bypass_users={bypass_users}")
        
            # 인증 정보 가져오기
            user_info = find_auth_by_field('userId', user_id)
            if not user_info:
                return create_response("인증 정보가 없습니다. 먼저 인증을 진행해 주세요.")
        
            id_code = user_info.get('id_code')
            name = user_info.get('name')
        
            # 여기서 비일상조사 시작
            survey_type = "비일상조사"
            select_path = ''
            msg, new_path = investigate_tree_logic(select_path, '', user_info, survey_type)
        
            # 로그 기록
            log_all(user_id, id_code, name, "[비일상조사-우회시작]", "test", "", msg)
        
            # 우회 종료 처리
            del bypass_users[user_id]
            print(f"DEBUG: [bypass_users 삭제] user_id={user_id}, bypass_users={bypass_users}")
        
            return create_response(msg)

        if user_input == "인증":
            msg = "인증 코드를 입력해 주세요."
            type_ = "auth"
            select_path = ""
            log_all(user_id, id_code, name, '[인증-요청]', type_, select_path, msg)
            return create_response(msg)

        # 조사 시작 전에 bypass 여부 확인
        if user_input == "조사":
            if user_id in bypass_users:
                survey_type = "비일상조사"
                print(f"DEBUG: [우회된 유저 비일상조사 시작] user_id={user_id}")
                del bypass_users[user_id]  # 한 번만 우회 가능하게
            else:
                survey_type = get_survey_type_by_day()
        
            msg, new_path = investigate_tree_logic(select_path, '', user_info, survey_type)
            log_all(user_id, id_code, name, f"[{survey_type} 시작]", "investigate", "", msg)
            return create_response(msg)

        if user_input == "정산":
            type_ = "settle_tree"  # 정산 후 인증 상태로 되돌림
            select_path = ""
            msg = calculate_auto_settlement(id_code, name)
            log_all(user_id, id_code, name, "[자동정산]", type_, "", msg)
            update_user_auth(user_id, id_code)
            return create_response(msg)

        if user_input == "소지금":
            msg = check_coin_balance(user_id)
            log_all(user_id, id_code, name, "[소지금 조회]", "check_coin", "", msg)
            return create_response(msg)

        if user_input == "조사 종료":
            # "조사 종료" 입력 시 원래 survey_type으로 복구
            survey_type = original_survey_type  # 원래 survey_type으로 되돌림
            msg = "조사를 종료하고, 원래 상태로 돌아갑니다."
            log_all(user_id, id_code, name, "[조사-종료]", "investigate_tree", "", msg)
            return create_response(msg)

        if type_ == 'auth':
            msg = "무엇을 진행하시겠습니까?\n\n▶ 조사"
            log_all(user_id, id_code, name, "[인증-유지]", type_, "", msg)
            return create_response(msg)

        elif type_ == 'investigate_tree':
            processed_input = extract_bracket_content(user_input) or user_input.strip()

            if processed_input in ["종료", "조사종료", "그만", "메인으로"]:
                msg = "조사를 종료합니다.\n무엇을 진행하시겠습니까?\n\n▶ 조사"
                log_all(user_id, id_code, name, "[조사트리-종료]", type_, "", msg)
                return create_response(msg)

            if not processed_input:
                msg = "조사 장소를 다시 선택해 주세요."
                log_all(user_id, id_code, name, "[조사트리-입력없음]", type_, "", msg)
                return create_response(msg)

            msg, new_path = investigate_tree_logic(select_path, processed_input, user_info, survey_type=survey_type)
            log_path = f"{select_path} > {processed_input}" if select_path else processed_input
            log_all(user_id, id_code, name, f"[조사트리] {log_path}", type_, new_path, msg)
            return create_response(msg)

        else:
            return create_response("잘못된 입력입니다. 인증·조사·정산 중 하나를 입력해주세요.")

    except Exception as e:
        print(f"서버 처리 오류: {e}")
        return create_response("서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")

@app.route('/', methods=['POST'])
def root_skill():
    return skill()

@app.route('/', methods=['GET'])
def index():
    return "챗봇 서버입니다. POST /skill 또는 POST / 경로로 요청해주세요.", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
