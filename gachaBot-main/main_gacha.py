from mastodon import Mastodon, StreamListener
import pymysql

from coin_module import handle_balance, handle_coin_transfer, handle_coin_gain, load_coin
from item_module import handle_gacha, handle_inventory, handle_item_search, handle_present, handle_gift, handle_item_sell
from util import clean_html_tags

# ====== 마스토돈 인증 ======
mastodon = Mastodon(
    access_token='mov89dn66Grg_Ikrql6ZxOv-kPxxRaBE7xBV12ddEzU',  # 토큰 변경 시 주의
    api_base_url='https://lockdownheaven.duckdns.org/'
)

# ====== MySQL 연결 ======
def get_conn():
    return pymysql.connect(
        host='35.209.172.242',
        user='admin',
        password='password1212',
        db='bot',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# ====== 마스토돈 리스너 ======
class GachaBotListener(StreamListener):
    def on_notification(self, notification):
        if notification['type'] != 'mention':
            return

        content = clean_html_tags(notification['status']['content'])
        username = notification['account']['display_name'].strip()
        acct = notification['account']['acct']
        status_id = notification['status']['id']

        conn = get_conn()
        try:
            reply = None

            # 명령어별 분기 처리
            if '[정산]' in content:
                reply = handle_balance(conn, mastodon, acct)
            elif '[뽑기]' in content or '[가챠]' in content:
                reply = handle_gacha(conn, acct, content)
            elif '[소지품]' in content or '[인벤토리]' in content or '[소지 아이템]' in content:
                reply = handle_inventory(conn, acct)
            elif '[양도]' in content:
                reply = handle_gift(conn, acct, content)
            elif '[선물]' in content:
                reply = handle_present(conn, acct, content)
            elif '[코인 양도]' in content:
                reply = handle_coin_transfer(conn, acct, content)
            elif '[코인 획득]' in content:
                reply = handle_coin_gain(conn, acct, content)
            elif '[아이템 매각]' in content or '[매각]' in content:
                reply = handle_item_sell(conn, acct, content)
            else:
                return
                

            if reply:
                # 문자열 분할 여부 판단
                if isinstance(reply, list):
                    reply_to_id = status_id
                    for part in reply:
                        status = mastodon.status_post(
                            status=f"@{acct} {part}",
                            in_reply_to_id=reply_to_id,
                            visibility='unlisted'
                        )
                        reply_to_id = status['id']
                else:
                    mastodon.status_post(
                        status=f"@{acct} {reply}",
                        in_reply_to_id=status_id,
                        visibility='unlisted'
                    )

        except Exception as e:
            print(f"[ERROR] 알림 처리 중 예외 발생: {e}")
        finally:
            conn.close()

# ====== 실행 ======
if __name__ == '__main__':
    print("🎁 GachaBot 실행 중...")
    mastodon.stream_user(GachaBotListener())
