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