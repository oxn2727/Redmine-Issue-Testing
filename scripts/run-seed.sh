#!/bin/sh
# 在 Redmine 容器里用【生产环境】跑一个 rails runner 脚本。
#
# 为什么需要这个包装：直接 docker exec ... sh -c "..." 时，
# Windows 的 cmd 会吃掉双引号、bash 会做路径转换，两边的引号转义规则还不一样。
# 把逻辑放进容器内的 .sh 文件，宿主机就只需要一条无引号的命令，彻底绕开转义问题。
#
# 用法（宿主机）：
#   docker exec redmin_test-redmine-1 sh /tmp/run-seed.sh /tmp/你的脚本.rb

cd /usr/src/redmine || exit 1

# Rails 只认 SECRET_KEY_BASE，而 Redmine 镜像只提供了 REDMINE_SECRET_KEY_BASE，需要显式转换
export SECRET_KEY_BASE="$REDMINE_SECRET_KEY_BASE"

RAILS_ENV=production bundle exec rails runner "$1"
