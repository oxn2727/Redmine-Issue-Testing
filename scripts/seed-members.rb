# 配置测试项目成员（幂等）：reporter1/developer1/manager1 加入项目 v1-0
p = Project.find_by(identifier: 'v1-0')
abort "项目 v1-0 不存在" if p.nil?

{
  'reporter1'  => 'Reporter',
  'developer1' => 'Developer',
  'manager1'   => 'Manager',
}.each do |login, role_name|
  u = User.find_by(login: login)
  if u.nil?
    puts "跳过 #{login}（用户不存在）"
    next
  end
  role = Role.find_by(name: role_name)
  if role.nil?
    puts "跳过 #{login}（角色 #{role_name} 不存在）"
    next
  end
  m = Member.find_by(project_id: p.id, user_id: u.id)
  if m.nil?
    m = Member.new(project_id: p.id, user_id: u.id)
    m.roles = [role]
    m.save!
    puts "新增成员：#{login} -> #{role_name}"
  else
    m.roles = [role]
    m.save!
    puts "更新成员：#{login} -> #{role_name}"
  end
end

puts ""
puts "当前项目成员："
p.members.reload.each do |m|
  puts "  #{m.principal}  =>  #{m.roles.map(&:name).join(',')}"
end
