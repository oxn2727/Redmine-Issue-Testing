# -*- coding: utf-8 -*-
# 补齐 Redmine 缺失的默认配置数据（跟踪标签 / 问题状态 / 枚举 / 默认查询）
# 不触碰已有的角色与角色权限
created = []

# ---------- 1. 问题状态 ----------
if IssueStatus.none?
  IssueStatus.create!(name: 'New',         is_closed: false, position: 1)
  IssueStatus.create!(name: 'In Progress', is_closed: false, position: 2)
  IssueStatus.create!(name: 'Resolved',    is_closed: false, position: 3)
  IssueStatus.create!(name: 'Feedback',    is_closed: false, position: 4)
  IssueStatus.create!(name: 'Closed',      is_closed: true,  position: 5)
  IssueStatus.create!(name: 'Rejected',    is_closed: true,  position: 6)
  created << "问题状态 x#{IssueStatus.count}"
else
  created << "问题状态已存在(跳过) x#{IssueStatus.count}"
end

# 默认状态：第一个未关闭、position 最小的
default_status = IssueStatus.where(is_closed: false).order(:position).first || IssueStatus.first

# ---------- 2. 跟踪标签 ----------
if Tracker.none?
  Tracker.create!(name: 'Bug',     default_status_id: default_status.id, is_in_roadmap: false, position: 1)
  Tracker.create!(name: 'Feature', default_status_id: default_status.id, is_in_roadmap: true,  position: 2)
  Tracker.create!(name: 'Support', default_status_id: default_status.id, is_in_roadmap: false, position: 3)
  Setting.default_projects_tracker_ids = Tracker.order(:position).pluck(:id).map(&:to_s)
  created << "跟踪标签 x#{Tracker.count}"
else
  created << "跟踪标签已存在(跳过) x#{Tracker.count}"
end

# ---------- 3. 把跟踪标签挂到现有项目上（否则建 Issue 时选不到类型） ----------
Project.all.each do |p|
  next unless p.trackers.empty?
  p.trackers = Tracker.all
  p.save!
  created << "项目[#{p.identifier}]关联了 #{Tracker.count} 个跟踪标签"
end

# ---------- 4. 枚举：优先级 / 文档分类 / 活动类型 ----------
if IssuePriority.none?
  IssuePriority.create!(name: 'Low',       position: 1)
  IssuePriority.create!(name: 'Normal',    position: 2, is_default: true)
  IssuePriority.create!(name: 'High',      position: 3)
  IssuePriority.create!(name: 'Urgent',    position: 4)
  IssuePriority.create!(name: 'Immediate', position: 5)
  created << "优先级 x#{IssuePriority.count}"
end

if DocumentCategory.none?
  DocumentCategory.create!(name: 'User documentation',      position: 1)
  DocumentCategory.create!(name: 'Technical documentation', position: 2)
  created << "文档分类 x#{DocumentCategory.count}"
end

if TimeEntryActivity.none?
  TimeEntryActivity.create!(name: 'Design',      position: 1)
  TimeEntryActivity.create!(name: 'Development', position: 2)
  created << "活动类型 x#{TimeEntryActivity.count}"
end

# ---------- 5. 默认查询（"指派给我"等便利入口） ----------
if IssueQuery.none?
  IssueQuery.create!(
    name: 'Assigned to me',
    filters: {'status_id' => {:operator => 'o', :values => ['']},
              'assigned_to_id' => {:operator => '=', :values => ['me']}},
    sort_criteria: [['priority', 'desc'], ['updated_on', 'desc']],
    visibility: Query::VISIBILITY_PUBLIC)
  IssueQuery.create!(
    name: 'Reported by me',
    filters: {'status_id' => {:operator => 'o', :values => ['']},
              'author_id' => {:operator => '=', :values => ['me']}},
    sort_criteria: [['updated_on', 'desc']],
    visibility: Query::VISIBILITY_PUBLIC)
  created << "默认查询 x#{IssueQuery.count}"
end

puts "===== 补齐结果 ====="
created.each { |c| puts "  - #{c}" }
puts "===== 当前状态 ====="
puts "  角色:        #{Role.order(:id).pluck(:id, :name).map { |i, n| "#{i}:#{n}" }.join(', ')}"
puts "  跟踪标签:    #{Tracker.order(:id).pluck(:id, :name).map { |i, n| "#{i}:#{n}" }.join(', ')}"
puts "  问题状态:    #{IssueStatus.order(:position).pluck(:id, :name).map { |i, n| "#{i}:#{n}" }.join(', ')}"
puts "  工作流规则:  #{WorkflowTransition.count} 条"
puts "  项目跟踪标签: #{Project.first&.trackers&.pluck(:name)&.join(', ')}"
