# 接口测试环境一键准备（幂等，重复跑无害）
#   1) 启用 REST API（不启用的话所有接口 403）
#   2) 给 admin / reporter1 / developer1 / manager1 各生成一个 API Key
#   3) 把三个测试账号加进测试项目（否则做不了权限/越权用例）
#   4) 补上问题类别与目标版本（"全部参数创建"用例需要）

puts "=" * 60
puts "Redmine 接口测试环境准备"
puts "=" * 60

# ---------- 1. 启用 REST API ----------
Setting.rest_api_enabled = '1'
puts "[1] 启用 REST API        : rest_api_enabled = #{Setting.rest_api_enabled}"

# ---------- 2. 生成 API Key ----------
puts ""
puts "[2] 各账号 API Key："
API_KEYS = {}
%w[admin reporter1 developer1 manager1].each do |login|
  u = User.find_by(login: login)
  if u.nil?
    puts "    #{login.ljust(12)} 用户不存在，跳过"
    next
  end
  t = Token.find_by(user_id: u.id, action: 'api')
  if t.nil?
    t = Token.new(user_id: u.id, action: 'api')
    t.value = SecureRandom.hex(20)
    t.save!
  end
  API_KEYS[login] = t.value
  puts "    #{login.ljust(12)} #{t.value}"
end

# ---------- 3. 配置项目成员 ----------
puts ""
puts "[3] 项目成员："
p = Project.find_by(identifier: 'v1-0')
if p.nil?
  puts "    项目 v1-0 不存在，跳过"
else
  {
    'reporter1'  => 'Reporter',
    'developer1' => 'Developer',
    'manager1'   => 'Manager',
  }.each do |login, role_name|
    u = User.find_by(login: login)
    role = Role.find_by(name: role_name)
    next if u.nil? || role.nil?
    m = Member.find_by(project_id: p.id, user_id: u.id)
    if m.nil?
      m = Member.new(project_id: p.id, user_id: u.id)
      m.roles = [role]
      m.save!
      puts "    #{login.ljust(12)} 已加入项目，角色 = #{role_name}"
    else
      m.roles = [role]
      m.save!
      puts "    #{login.ljust(12)} 已在项目中，角色 = #{role_name}"
    end
  end

  # ---------- 4. 问题类别与目标版本 ----------
  puts ""
  puts "[4] 问题类别 / 目标版本："
  %w[前端 后端 数据库].each do |name|
    c = p.issue_categories.find_by(name: name)
    c = p.issue_categories.create!(name: name) if c.nil?
  end
  puts "    类别：" + p.issue_categories.map { |c| "#{c.id}=#{c.name}" }.join(", ")

  [['V1.1', 'open'], ['V2.0', 'open']].each do |name, status|
    v = p.versions.find_by(name: name)
    v = p.versions.create!(name: name, status: status, sharing: 'none') if v.nil?
  end
  puts "    版本：" + p.versions.map { |v| "#{v.id}=#{v.name}" }.join(", ")
end

puts ""
puts "=" * 60
puts "完成。把上面的 Key 填进 api_tests/config.py 即可。"
puts "=" * 60
