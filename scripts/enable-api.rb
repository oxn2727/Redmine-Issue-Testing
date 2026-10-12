# 一次性把接口测试环境备齐：启用 REST API + 为测试账号生成 API Key
Setting.rest_api_enabled = '1'
Setting.login_required = '0' if Setting.login_required.nil?
puts "rest_api_enabled = #{Setting.rest_api_enabled}"

%w[admin reporter1 developer1 manager1].each do |login|
  u = User.find_by(login: login)
  next if u.nil?
  t = Token.find_by(user_id: u.id, action: 'api')
  if t.nil?
    t = Token.new(user_id: u.id, action: 'api')
    t.value = SecureRandom.hex(20)
    t.save!
  end
  puts "#{login}\t#{t.value}"
end
