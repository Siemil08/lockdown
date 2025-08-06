import pymysql
from flask import Flask, request
from auth import find_auth_by_field, find_auth_by_id_code, find_auth_by_user_id, update_user_auth, require_auth
from investigate import investigate_tree_logic
from settlement import calculate_auto_settlement, check_coin_balance
from utils2 import get_conn, create_response, log_all, get_user_status, get_survey_type_by_day, extract_bracket_content, is_long_time_no_see
from datetime import datetime
import pytz

KST = pytz.timezone('Asia/Seoul')
bypass_users = {}  # user_id: 입력한 키 저장
original_survey_types = {}  # user_id 별 원래 survey_type 저장

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
    try:
        data = request.json
        user_request = data.get('userRequest', {})
        user_id = user_request.get('user', {}).get('id', '')
        user_input = user_request.get('utterance', '').strip()

        # 디버그: 요청 기본 정보 출력
        print(f"[DEBUG] 요청 user_id: {user_id}, user_input: '{user_input}'")

        force_key = load_key()

        user_info = find_auth_by_field('userId', user_id)

        # 인증 관련 디버그
        print(f"[DEBUG] user_info: {user_info}")

        if not user_info or user_input.isdigit():
            auth_row = find_auth_by_id_code(user_input)
            if auth_row:
                name = auth_row.get('name', '사용자')
                id_code = user_input
                update_user_auth(user_id, id_code)
                msg = f"{name}님 인증 완료!\n무엇을 진행하시겠습니까?\n\n▶ 조사"
                log_all(user_id, id_code, name, "[인증-자동]", "auth", "", msg)
                print(f"[DEBUG] 인증 완료: id_code={id_code}, name={name}")
                return create_response(msg)
            elif not user_info:
                print(f"[DEBUG] 인증 필요: user_id={user_id}")
                return require_auth(user_id)

        id_code = user_info['id_code']
        name = user_info['name']
        status = get_user_status(user_id)

        # 상태 관련 디버그
        print(f"[DEBUG] user_status: {status}")

        type_ = status['type']
        select_path = status['select_path']
        survey_type = get_survey_type_by_day()

        # 상태 및 입력값 디버그 출력
        print(f"[DEBUG] type_: {type_}, select_path: '{select_path}', survey_type: {survey_type}")

        if is_long_time_no_see(user_info.get('auth_time', '')):
            update_user_auth(user_id, id_code)

        if user_input == force_key:
            bypass_users[user_id] = force_key
            msg = "키가 확인되었습니다. 비일상조사 테스트에 진입합니다.\n조사를 입력하여 테스트를 진행해 주세요."
            log_all(user_id, id_code, name, "[테스트-키확인]", "test", "", msg)
            print(f"[DEBUG] 비일상조사 테스트 모드 진입: user_id={user_id}")
            return create_response(msg)

        if user_id in bypass_users and bypass_users[user_id] == force_key:
            original_survey_types[user_id] = survey_type
            survey_type = "비일상조사"
            type_ = 'test'

            processed_input = extract_bracket_content(user_input) or user_input.strip()

            print(f"[DEBUG] 비일상조사 모드 input: '{processed_input}'")

            if processed_input in ["종료", "조사종료", "그만", "메인으로"]:
                msg = "조사를 종료합니다.\n무엇을 진행하시겠습니까?\n\n▶ 조사"
                log_all(user_id, id_code, name, "[조사트리-종료]", type_, "", msg)
                survey_type = original_survey_types.get(user_id, get_survey_type_by_day())
                del bypass_users[user_id]
                original_survey_types.pop(user_id, None)
                print(f"[DEBUG] 비일상조사 종료: user_id={user_id}")
                return create_response(msg)

            if not processed_input:
                msg = "조사 장소를 다시 선택해 주세요."
                log_all(user_id, id_code, name, "[조사트리-입력없음]", type_, "", msg)
                return create_response(msg)

            msg, new_path = investigate_tree_logic(select_path, processed_input, user_info, survey_type=survey_type)
            log_path = f"{select_path} > {processed_input}" if select_path else processed_input
            log_all(user_id, id_code, name, f"[조사트리] {log_path}", type_, new_path, msg)
            print(f"[DEBUG] 조사트리 진행: new_path='{new_path}'")
            return create_response(msg)

        # 이하 일반 처리 부분도 디버그 추가 가능

        if user_input == "인증":
            msg = "인증 코드를 입력해 주세요."
            type_ = "auth"
            select_path = ""
            log_all(user_id, id_code, name, '[인증-요청]', type_, select_path, msg)
            print(f"[DEBUG] 인증 요청 처리")
            return create_response(msg)

        if user_input == "조사":
            msg, new_path = investigate_tree_logic(select_path, '', user_info, survey_type)
            log_all(user_id, id_code, name, f"[{survey_type} 시작]", "investigate", "", msg)
            print(f"[DEBUG] 조사 시작: new_path='{new_path}'")
            return create_response(msg)

        if user_input == "정산":
            type_ = "settle_tree"
            select_path = ""
            msg = calculate_auto_settlement(id_code, name)
            log_all(user_id, id_code, name, "[자동정산]", type_, "", msg)
            update_user_auth(user_id, id_code)
            print(f"[DEBUG] 정산 처리 완료")
            return create_response(msg)

        if user_input == "소지금":
            msg = check_coin_balance(user_id)
            log_all(user_id, id_code, name, "[소지금 조회]", "check_coin", "", msg)
            print(f"[DEBUG] 소지금 조회")
            return create_response(msg)

        if user_input == "조사 종료":
            msg = "조사를 종료합니다.\n무엇을 진행하시겠습니까?\n\n▶ 조사"
            log_all(user_id, id_code, name, "[조사-종료]", "investigate_tree", "", msg)
            print(f"[DEBUG] 조사 종료 처리")
            return create_response(msg)

        if type_ == 'auth':
            msg = "무엇을 진행하시겠습니까?\n\n▶ 조사"
            log_all(user_id, id_code, name, "[인증-유지]", type_, "", msg)
            print(f"[DEBUG] 인증 상태 유지")
            return create_response(msg)

        elif type_ == 'investigate_tree':
            processed_input = extract_bracket_content(user_input) or user_input.strip()
            print(f"[DEBUG] 조사트리 입력 처리: '{processed_input}'")

            if processed_input in ["종료", "조사종료", "그만", "메인으로"]:
                msg = "조사를 종료합니다.\n무엇을 진행하시겠습니까?\n\n▶ 조사"
                log_all(user_id, id_code, name, "[조사트리-종료]", type_, "", msg)
                print(f"[DEBUG] 조사트리 종료")
                return create_response(msg)

            if not processed_input:
                msg = "조사 장소를 다시 선택해 주세요."
                log_all(user_id, id_code, name, "[조사트리-입력없음]", type_, "", msg)
                print(f"[DEBUG] 조사트리 입력없음")
                return create_response(msg)

            msg, new_path = investigate_tree_logic(select_path, processed_input, user_info, survey_type=survey_type)
            log_path = f"{select_path} > {processed_input}" if select_path else processed_input
            log_all(user_id, id_code, name, f"[조사트리] {log_path}", type_, new_path, msg)
            print(f"[DEBUG] 조사트리 진행: new_path='{new_path}'")
            return create_response(msg)

        else:
            print(f"[DEBUG] 잘못된 입력: '{user_input}'")
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
