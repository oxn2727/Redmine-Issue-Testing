@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo  Redmine 测试账号密码重置（带当场校验）
echo ============================================================
echo.

echo [0/2] 检查容器是否在运行...
docker ps --format "{{.Names}}" | findstr /C:"redmin_test-redmine-1" >nul
if errorlevel 1 (
    echo.
    echo [提示] 容器 redmin_test-redmine-1 没在运行。
    echo         请先双击 start-redmine.cmd 把环境启动起来，再跑本脚本。
    echo.
    pause
    exit /b 1
)

echo [1/2] 复制脚本进容器...
docker cp run-seed.sh redmin_test-redmine-1:/tmp/run-seed.sh
if errorlevel 1 goto :fail
docker cp reset-passwords.rb redmin_test-redmine-1:/tmp/reset_passwords.rb
if errorlevel 1 goto :fail

echo.
echo [2/2] 执行：重置 4 个账号密码并校验
echo.
docker exec redmin_test-redmine-1 sh /tmp/run-seed.sh /tmp/reset_passwords.rb
if errorlevel 1 goto :fail

echo.
echo 完成。密码统一为 Test@1234
echo 登录地址：http://localhost:3000
echo.
pause
exit /b 0

:fail
echo.
echo [失败] 请把上面的报错整段发给我。
echo.
pause
exit /b 1
