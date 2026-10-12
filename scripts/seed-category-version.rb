# 给测试项目补上「问题类别」和「目标版本」（幂等）
# 用途：F1-10「关联目标版本」、接口用例「全部参数创建」需要它们存在
p = Project.find_by(identifier: 'v1-0')
abort "项目 v1-0 不存在" if p.nil?

%w[前端 后端 数据库].each do |name|
  c = p.issue_categories.find_by(name: name)
  if c.nil?
    c = p.issue_categories.create!(name: name)
    puts "新增类别：#{c.name} (id=#{c.id})"
  else
    puts "类别已存在：#{c.name} (id=#{c.id})"
  end
end

[['V1.1', 'open'], ['V2.0', 'open']].each do |name, status|
  v = p.versions.find_by(name: name)
  if v.nil?
    v = p.versions.create!(name: name, status: status, sharing: 'none')
    puts "新增版本：#{v.name} (id=#{v.id})"
  else
    puts "版本已存在：#{v.name} (id=#{v.id})"
  end
end

puts ""
puts "类别列表：" + p.issue_categories.map { |c| "#{c.id}=#{c.name}" }.join(", ")
puts "版本列表：" + p.versions.map { |v| "#{v.id}=#{v.name}" }.join(", ")
