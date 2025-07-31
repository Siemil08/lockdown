import re
from datetime import datetime
from utils2 import get_conn
import pymysql

def extract_coin_from_text(text):
    patterns = [
        r"코인(?:을)?\s*(\d+)\s*개\s*(?:획득|습득|받|얻)",
        r"(\d+)\s*개\s*코인(?:을)?\s*(?:획득|습득|받|얻)",
        r"(\d+)\s*코인\s*(?:획득|습득|받|얻)",
        r"코인\s*(\d+)\s*개",
        r"(\d+)\s*코인",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            print(f"[DEBUG] 코인 감지됨: {match.group(1)}")
            return int(match.group(1))
    
    print("[DEBUG] 코인 관련 문구 없음")
    return 0


def calculate_auto_settlement(id_code, name):
    try:
        print(f"[DEBUG] 정산 시작 - id_code: {id_code}, name: {name}")
        conn = get_conn()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # 1) 현재 소지금 조회
            print("[DEBUG] auth 테이블에서 현재 코인 조회")
            cur.execute("SELECT coin FROM auth WHERE id_code = %s", (id_code,))
            row = cur.fetchone()
            if not row:
                print("[ERROR] 사용자 정보 없음")
                return "인증된 사용자를 찾을 수 없습니다."

            current_coin = int(row.get("coin") or 0)
            print(f"[DEBUG] 현재 코인: {current_coin}")

            # 2) Total_log 테이블에서 마지막 정산 이후 조사 로그 추출
            print("[DEBUG] Total_log 테이블에서 조사 로그 조회")
            cur.execute("""
                SELECT timestamp, type, bot_response
                FROM Total_log
                WHERE id_code = %s
                ORDER BY timestamp DESC
            """, (id_code,))
            logs = cur.fetchall()
            print(f"[DEBUG] 로그 개수: {len(logs)}개")

            total_new_coin = 0
            for log in logs:
                log_type = log["type"]
                log_time = log["timestamp"]
                print(f"[DEBUG] 로그 처리 중 - type: {log_type}, time: {log_time}")

                if log_type == "settle_tree":
                    print("[DEBUG] 마지막 정산 시점 도달 - 루프 종료")
                    break
                if log_type == "investigate_tree":
                    coin = extract_coin_from_text(log["bot_response"])
                    total_new_coin += coin
                    print(f"[DEBUG] 누적 코인 증가: +{coin} -> {total_new_coin}")

            # 3) 새로운 소지금 업데이트
            new_coin = current_coin + total_new_coin
            print(f"[DEBUG] 코인 업데이트: {current_coin} + {total_new_coin} = {new_coin}")
            cur.execute("UPDATE auth SET coin = %s WHERE id_code = %s", (new_coin, id_code))
            conn.commit()
            print("[DEBUG] 정산 완료 및 DB 반영 완료")

            return f"금일 일반 조사를 통해 {total_new_coin} 코인을 획득하였습니다.\n{name}님 현재 소지 코인은 {new_coin}개 입니다."

    except Exception as e:
        print(f"[ERROR] 자동 정산 오류: {e}")
        return "정산 중 오류가 발생했습니다."
    finally:
        conn.close()
        print("[DEBUG] DB 연결 종료")


def check_coin_balance(id_code):
    try:
        print(f"[DEBUG] 소지금 확인 시작 - id_code: {id_code}")
        conn = get_conn()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT name, coin FROM auth WHERE id_code = %s", (id_code,))
            row = cur.fetchone()
            if not row:
                print("[ERROR] 사용자 정보 없음")
                return "인증된 사용자를 찾을 수 없습니다."

            name = row.get("name", "사용자")
            coin = row.get("coin", 0)
            print(f"[DEBUG] {name}님의 현재 코인: {coin}")
            return f"{name}님의 현재 소지 코인은 {coin}개 입니다."

    except Exception as e:
        print(f"[ERROR] 소지금 확인 오류: {e}")
        return "소지금 확인 중 오류가 발생했습니다."
    finally:
        conn.close()
        print("[DEBUG] DB 연결 종료")
