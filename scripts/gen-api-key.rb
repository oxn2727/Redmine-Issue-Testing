# 为 admin 生成一个 REST API Key（幂等：已存在就复用）
u = User.find_by(login: 'admin')
t = Token.find_by(user_id: u.id, action: 'api')
if t.nil?
  t = Token.new(user_id: u.id, action: 'api')
  t.value = SecureRandom.hex(20)
  t.save!
  puts "NEW API KEY CREATED"
else
  puts "API KEY ALREADY EXISTS"
end
puts t.value
