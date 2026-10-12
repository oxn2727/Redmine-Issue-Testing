@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo  Redmine 接口测试环境准备
echo ============================================================
echo.

echo [1/2] 复制脚本进容器...
docker cp run-seed.sh redmin_test-redmine-1:/tmp/run-seed.sh
if errorlevel 1 goto :fail
docker cp setup-api-env.rb redmin_test-redmine-1:/tmp/setup_api_env.rb
if errorlevel 1 goto :fail

echo.
echo [2/2] 执行：启用 REST API + 生成 API Key + 配项目成员 + 建类别版本
echo.
docker exec redmin_test-redmine-1 sh /tmp/run-seed.sh /tmp/setup_api_env.rb
if errorlevel 1 goto :fail

echo.
echo 完成。把上面打印的 Key 填进 api_tests\config.py 即可跑用例。
echo.
pause
exit /b 0

:fail
echo.
echo [失败] 请依次检查：
echo   1) Docker Desktop 是否已启动
echo   2) 容器是否在运行：docker ps
echo   3) 容器没起的话，先跑 start-redmine.cmd
echo.
pause
exit /b 1
