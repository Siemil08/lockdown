# Mybot

# 카카오톡 챗봇 (Mybot) GCP 배포 가이드

## 1. GCP 설정

### VM 인스턴스 생성
- GCP 콘솔 > Compute Engine > VM 인스턴스 생성
- OS: Ubuntu 20.04 LTS 이상 권장
- 머신 타입: 최소 e2-micro 이상 권장
- 방화벽: HTTP, HTTPS, 3606, 5000

### 서비스 계정 생성 및 권한 설정
- GCP 콘솔에서 서비스 계정 생성 후 JSON 키 파일 다운로드
- 구글 시트 문서 공유 설정에서 서비스 계정 이메일을 편집 권한으로 추가

## AWS 설정시
- t2.medium 이상.
- OS: Ubuntu 20.04 LTS 이상 권장
인바운드 규칙으로 ssh, http, https, 사용자 지정 TCP 5000 풀어야함

## 2. SSH 접속 및 환경 세팅

```bash
sudo apt update
sudo apt install python3-full python3-venv -y

# 가상환경 생성
python3 -m venv venv

# 가상환경 활성화
source venv/bin/activate

sudo apt install python3 python3-pip -y
```

## 3. 카카오 비즈니스 설정
- 카카오톡 비즈니스센터에서 챗봇 및 스킬 서버 설정 진행 (자세한 내용은 카카오 개발자 문서 참고)
  - 비지니스 채널 개설
  - 스킬생성, url에 http://공개ip:5000/skill 양식으로 입력
  - 설정 후 왼쪽 메뉴에서 배포선택, 파란 배포버튼 클릭
    
## 4. mysql 셋팅
```bash
#/etc/mysql/my.cnf 또는 /etc/mysql/mysql.conf.d/mysqld.cnf
vi /etc/mysql/mysql.conf.d/mysqld.cnf
# bind-address = 0.0.0.0으로 수정 -> 저장
sudo systemctl restart mysql
sudo mysql
```
```sql
CREATE DATABASE IF NOT EXISTS bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'admin'@'%' IDENTIFIED BY 'ahrvysmswkehdghk';
GRANT ALL PRIVILEGES ON bot.* TO 'admin'@'%';
FLUSH PRIVILEGES;
exit
```
```bash
mysql -h your_ip -u admin -p bot
sudo ufw status verbose
sudo ufw allow 3306/tcp
sudo ufw enable
```
## 5. GCP에서 앱 구동
### 프로젝트 클론 및 의존성 설치
```bash
git clone https://Siemil08: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@github.com/Siemil08/Mybot.git
cd Mybot
pip install -r requirements.txt
# requirements.txt가 없으면 아래처럼 직접 설치
pip install Flask pymysql gspread pandas google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client oauth2client mysql-connector-python
```
### 앱 실행
```bash
python3 sync_sheet_to_mysql.py
python3 main.py
```
### 코드 수정 후 업데이트
```bash
git pull
```

## 6. http --> https 
1. Nginx 설치 및 설정
```bash
sudo apt update
sudo apt install nginx -y
sudo apt install certbot python3-certbot-nginx

# 기본 프록시 패스 설정
sudo vi /etc/nginx/sites-available/default
````
2. 예시 Nginx 설정 (/etc/nginx/sites-available/myapp)
```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;  # Flask 앱 주소 (localhost:5000)
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 7. 백그라운드 실행 및 유지
### screen 사용 (권장)
```bash
sudo apt install screen
screen -S mybot
python3 main.py
# 실행 중에 Ctrl + A, D 키를 눌러 세션 분리 (백그라운드 실행 유지)

# 재접속 및 서버 재시작 방법
screen -r mybot  # 분리된 세션에 다시 접속
# 서버를 종료하려면 Ctrl + C 입력
# 코드 수정 후 다시 실행: python3 main.py
# 다시 분리하려면 Ctrl + A, D
```
### nohup 사용
```
nohup python3 main.py &
# 실행 결과는 nohup.out 파일에 기록됨

# 서버 프로세스 종료 방법
sudo lsof -i :5000  # 5000번 포트 사용 중인 프로세스 확인
sudo kill -9 <PID>  # 해당 PID 프로세스 강제 종료

# 코드 수정 후 서버 재시작
nohup python3 main.py &
```
nohup은 터미널을 꺼도 애플리케이션이 꺼지지 않도록 하는 명령어
&는 애플리케이션이 백그라운드에서 돌아갈 수 있도록 하는 명령어


### 오후 9시마다 정기적으로 실행
```
#파이썬 위치 확인
which python3
# ==> /usr/bin/python3

# 자동 실행 스크립트 작성
crontab -e

# 에디터는 편한 것으로.
# 아래 입력
0 21 * * * /usr/bin/python3 /home/perfectbro_dpb/Mybot/sync_mysql_to_sheet.py >> /home/perfectbro_dpb/Mybot/mysql_to_sheet.log 2>&1
0 22 * * * /usr/bin/python3 /home/perfectbro_dpb/Mybot/sync_sheet_to_mysql.py >> /home/perfectbro_dpb/Mybot/sheet_to_mysql.log 2>&1

# 크론 확인
crontab -l
```
