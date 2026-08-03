@echo off
setlocal

set SQL_FILE=init_sql.sql

if not exist "%SQL_FILE%" (
    echo Error: SQL file %SQL_FILE% not found.
    exit /b 1
)

python ..\common\initialize_mysql.py
if errorlevel 1 (
    exit /b 1
)

python ..\common\initialize_eno4j.py
if errorlevel 1 (
    exit /b 1
)

exit /b 0
