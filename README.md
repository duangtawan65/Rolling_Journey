# Rolling_Journey

python -m venv venv  
cd ROLLING_JOURNEY
venv\Scripts\Activate

pip install -r requirements.txt

สร้างไฟล์ .env ใน Rolling_Journey\journey\.env จากนั้น วาง api key แนะสร้าง groq
api_key = วางตรงนี้


สร้าง database 

1. เปิด PowerShell แล้วเข้าสู่ psql shell ด้วย user postgres:
psql -U postgres

2. เมื่อเข้า psql ได้ ให้รันคำสั่งนี้ทีละบรรทัด:
CREATE DATABASE journey_db;
CREATE USER postgres WITH PASSWORD '1234'; 
GRANT ALL PRIVILEGES ON DATABASE journey_db TO postgres;

3. ออกจาก psql ด้วยคำสั่ง
\q

python manage.py makemigrations
python manage.py migrate

python manage.py runserver 


# ขั้นตอนการเชื่อมต่อ Clickhouse

ติดตั้ง clickhouseที่ใช้ >> pip install clickhouse-connect

# แก้ journey/journey/settings.py
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "journey_db"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", "1234"),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# ตั้งค่า Environment (.env)
สร้างไฟล์ .env ที่ Rolling_Journey/journey/.env
เพื่อใส่ค่า api_key = " ใส่ key ของตัวเอง "
DB_NAME=journey_db
DB_USER=postgres
DB_PASSWORD=1234
DB_HOST=127.0.0.1
DB_PORT=5432

# ClickHouse
CH_HOST=localhost
CH_PORT=8123
CH_USER=default
CH_PASSWORD=1234
CH_DATABASE=default

# สร้างฐานข้อมูล PostgreSQL
psql -U postgres

-- รันทีละบรรทัดใน psql
CREATE DATABASE journey_db;
CREATE USER postgres WITH PASSWORD '1234';
GRANT ALL PRIVILEGES ON DATABASE journey_db TO postgres;

เสร็จแล้วออกจาก database >> \q

# Migrate และรันเซิร์ฟเวอร์ ตามลำดับ 
python manage.py makemigrations
python manage.py migrate
python manage.py runserver

#  ตั้งค่า ClickHouse
สร้างไฟล์ docker-compose.yml ที่รากโปรเจกต์ 
สร้างตาราง ClickHouse สำหรับ Event Log
clickhouse/ แล้วสร้างไฟล์ init_eventlog.sql ตามโครงสร้างนี้ Rolling_Journey\clickhouse 

# เปิดใช้งาน Docker 
เปิด docker ขึ้นมาแล้วค่อยรันคำสั่งด้านล่างในเทอมินอล
docker compose up -d
docker ps

# สคริปต์ Sync Django → ClickHouse
สร้างไฟล์ journey/roll/sync_to_clickhouse.py
cd เข้าโฟลเดอร์ journey
cd journey
python -m roll.sync_to_clickhouse
หรือ 
รันจากรากโปรเจกต์
$env:PYTHONPATH = (Get-Location)
python -m journey.roll.sync_to_clickhouse

# กลับมารากโปรเจ็กต์ (ถ้ายังอยู่ใน journey ให้ cd ..)
cd ..
python .\journey\roll\sync_to_clickhouse.py
ถ้าเห็น No event logs to sync. = ยังไม่มี EventLog ใน Django

ถ้ามีข้อมูล = จะขึ้น ✅ Inserted N rows into ClickHouse

ตรวจสอบข้อมูลใน clickhouse ต้องมี EventLog ออกมา 
docker exec -it clickhouse clickhouse-client --query "SELECT count() FROM event_log"
docker exec -it clickhouse clickhouse-client --query "SELECT * FROM event_log ORDER BY ts DESC LIMIT 5"

# สร้าง dashboard

โหลดค่าพวกนี้ใน journey/journey/settings.py
(วางไว้ท้ายไฟล์ หรือโซนตั้งค่าฐานข้อมูล)
CLICKHOUSE = {
    "HOST": os.getenv("CH_HOST", "localhost"),
    "PORT": int(os.getenv("CH_PORT", "8123")),
    "USER": os.getenv("CH_USER", "default"),
    "PASSWORD": os.getenv("CH_PASSWORD", ""),
    "DATABASE": os.getenv("CH_DATABASE", "default"),
}
เขียนฟังก์ชันที่ดึงข้อมูลมาจาก Clickhouse ลงใน view.py
เพิ่มพาธของแดชบอร์ด ใน journey/roll/urls.py
สร้างเทมเพลตและกราฟ สร้างไฟล์ journey/roll/templates/roll/native_dashboard.html

รันและเปิดหน้าแดชบอร์ด
cd journey
python manage.py runserver 
แล้วเปิดเบราว์เซอร์ไปที่ http://localhost:8000/dashboard/




