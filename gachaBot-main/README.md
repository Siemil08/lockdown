# GachaBot

---

## GCP 설정

1. **Compute Engine > VM 인스턴스 생성**  
   - OS: Ubuntu 20.04 LTS 권장  
   - 머신 타입: 최소한 e2-micro  
   - 방화벽: HTTP, HTTPS 허용, 3306, 5000

2. **구글 클라우드 콘솔에서 서비스 계정 생성 및 JSON 키 파일 다운로드**  
   - GCP 콘솔에서 서비스 계정 생성
   - 키 유형: JSON
   - 생성된 JSON 키 파일은 GachaBot.py가 위치한 서버에 업로드

3. **구글 시트 공유 설정**
   - 해당 Google Sheet 문서에 서비스 계정 이메일을 추가
   -  권한: 편집자
     
4.  **VM 환경 세팅**
   ```bash
   sudo apt update
   sudo apt install python3 python3-pip screen -y
   pip3 install gspread google-auth Mastodon.py pymysql mysql-connector-python pandas
   ```

5. **MySQL 설정**
   1. MySQL 서버 시작 및 자동 실행 설정
   ```
   bash
   sudo systemctl start mysql
   sudo systemctl enable mysql
    ```
   2. root 비밀번호 설정 및 외부 접속 허용
   ```
   bash
   sudo mysql -u root
   sudo vi /etc/mysql/mysql.conf.d/mysqld.cnf
    ```
   MySQL 접속 후:
    ```
   sql
   ALTER USER 'root'@'localhost' IDENTIFIED BY '비밀번호';
   FLUSH PRIVILEGES;
   UPDATE mysql.user SET host='%' WHERE user='root' AND host='localhost';
   EXIT;
   ```
   3. 사용자 생성 및 권한 부여
   ```
   bash
   mysql -u root -p
   ```
   bind-address = 0.0.0.0 → ✅ 외부 접속 허용
   
   입장 후 :
   ```
   sql
   create user 'admin'@'%'identified by 'ahrvysmswkehdghk'
   GRANT ALL PRIVILEGES ON bot.* TO 'gacha'@'%';
   FLUSH PRIVILEGES;

   create database bot;

   ### 1. 테이블 생성 SQL (DDL)
```sql
-- 인증 시트
CREATE TABLE IF NOT EXISTS auth (
    id_code VARCHAR(64) PRIMARY KEY,
    name varchar(64),
    userId VARCHAR(64),
    job varchar(64),
    height FLOAT,
    --attention INT, 주목도 
    power INT, --근력
    obs int, --관찰력
    luck INT, --행운
    wilpower int, --지력
    coin INT null, --소지금
    gain_path TEXT null, --획득 경로
    auth_time DATETIME null--인증시각
);

-- 정산시트
CREATE TABLE IF NOT EXISTS settlements (
    name VARCHAR(64) PRIMARY KEY,
    inventory TEXT null,
    sell_pending TEXT null,
    tweet_count INT null, --툿수
    last_tweet_count INT null, --정산 대기
    pending_count INT null,--정산 툿수
    total_coin INT null, --지불 코인
    updated_at DATETIME null--마지막 정산
);

-- 호감도
CREATE TABLE IF NOT EXISTS favor (
   name varchar(64) primary key,
   favor_items TEXT, --좋템
   dislike_items TEXT null, --싫템
   favor_score JSON null, --호감점수
   favor_status TEXT null, --호감도 현황
   complete TEXT null --컴플리트
);

-- 가챠
create table gacha(
    id int AUTO_INCREMENT primary key,
    items text);
);

-- 봇입금
CREATE TABLE bot_input (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    bot_response TEXT NOT NULL
);
  
   EXIT;
   ```
![image](https://github.com/user-attachments/assets/e68c6b23-3324-4e6f-abe2-50f6bd5f728d)

---
## Mastodon API 설정

1. 마스토돈 계정 로그인 → 설정 → 개발 → 새로운 어플리케이션 등록 클릭  
2. 범위는 read, write (빨간 글씨만 체크) → 아래로 내려서 제출 버튼 클릭해 Access Token 발급  
3. `GachaBot.py` 파일의 `mastodon = Mastodon()` 생성자 부분에  
- access_token  
- api_base_url (인스턴스 주소)  
넣고 수정하기

---

## GCP 앱 구동

1. **SSH 접속 후 프로젝트 클론 및 의존성 설치**
   
   ```bash
   git clone https://Siemil08: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@github.com/Siemil08/gachaBot.git
   cd gachaBot
   pip install Mastodon.py gspread google-auth
   python3 GachaBot.py

 - 코드 수정이 있는 경우
   ```bash
   git pull

2. **백그라운드 실행 및 유지**
- screen 또는 tmux 사용해 터미널 세션 분리
- 또는 nohup으로 실행 후 터미널 닫아도 유지 가능
  
   ```bash
   sudo apt install screen
   screen -S gachabot
   python3 GachaBot.py
   
- Ctrl+A, D 눌러 세션 분리 (백그라운드 실행 유지)
```bash
nohup python3 GachaBot.py &
crontab -e
0 * * * * /usr/bin/python3 /home/ubuntu/gachaBot/sync_mysql_to_sheet.py >> /home/ubuntu/mysql_to_sheet.log 2>&1
```
- 1시간 간격 실행
   - 매 10분 간격: */10 * * * *
   - 매일 자정 1회: 0 0 * * *
   - 매 6시간마다: 0 */6 * * *


