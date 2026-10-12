# 重置测试账号密码，并【当场校验】确保真的生效
#
# 为什么要这个脚本：
#   Redmine 的 User#save 在密码不满足复杂度校验时会【静默返回 false】，
#   密码字段一点不改，但表面看脚本"跑完了"。所以本脚本每个账号都做二次验证：
#   写完 -> reload -> check_password? 必须为 true，否则明确报错。
#
# 用法见同目录 reset-passwords.cmd（一键）。

NEW_PW = 'Test@1234'
LOGINS = %w[admin reporter1 developer1 manager1]

puts "目标密码：#{NEW_PW}"
puts "-" * 52

failed = []
LOGINS.each do |login|
  u = User.find_by(login: login)
  if u.nil?
    puts "#{login.ljust(11)} 账号不存在 -> 跳过"
    failed << login
    next
  end

  u.password = NEW_PW
  u.password_confirmation = NEW_PW
  # 顺带保证账号是可登录状态（1 = active）
  u.status = User::STATUS_ACTIVE

  saved = u.save
  u.reload
  ok = u.check_password?(NEW_PW)

  if saved && ok
    puts "#{login.ljust(11)} 已重置  check_password? = true   status=#{u.status}"
  else
    failed << login
    puts "#{login.ljust(11)} 【失败】save=#{saved} check_password?=#{ok}"
    puts "            校验错误：#{u.errors.full_messages.join('; ')}" unless u.errors.empty?
  end
end

puts "-" * 52
if failed.empty?
  puts "全部 #{LOGINS.size} 个账号已可用，密码统一为 #{NEW_PW}"
  puts ""
  puts "登录地址：http://localhost:3000"
  puts "账号：admin / reporter1 / developer1 / manager1"
  puts ""
  puts "想改回自己的密码：登录后右上角「My account / 我的账号」->「修改密码」。"
else
  puts "有 #{failed.size} 个账号失败：#{failed.join(', ')}"
  puts "请把上面的完整输出发我。"
  exit 1
end
