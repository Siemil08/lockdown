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
                id산"
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
