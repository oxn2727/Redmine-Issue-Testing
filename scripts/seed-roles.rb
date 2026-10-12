# -*- coding: utf-8 -*-
# ============================================================
# Redmine 三个测试角色的权限一键校正
# 依据：Redmine 官方默认权限（lib/redmine/default_data/loader.rb）+ 本项目测试需求
# 为什么要校正：之前界面手工勾选时容易漏勾、误勾
#   · Reporter 误勾了「管理版本库」（官方默认没有，属越权）
#   · Developer 漏勾了「管理版本」「管理问题类别」（影响 F1-10、F3 用例）
# 特性：幂等 —— 重复跑结果一样，直接把权限覆盖成标准值
# ============================================================

# ---------- Reporter（报告者）：官方默认 19 项 + edit_own_issues ----------
# 加 edit_own_issues 的原因：本项目第三节给 Reporter 配了「新建↔反馈」的工作流，
# 没有这个权限的话工作流配了也不生效（工作流是"路"，权限是"门"）
REPORTER_PERMS = %i[
  view_issues add_issues add_issue_notes save_queries
  view_gantt view_calendar
  log_time view_time_entries
  view_news comment_news
  view_documents
  view_wiki_pages view_wiki_edits
  view_messages add_messages edit_own_messages
  view_files browse_repository view_changesets
  edit_own_issues
]

# ---------- Developer（开发者）：官方默认 31 项 ----------
DEVELOPER_PERMS = %i[
  manage_versions manage_categories
  view_issues add_issues edit_issues
  view_private_notes set_notes_private
  manage_issue_relations manage_subtasks
  add_issue_notes save_queries
  view_gantt view_calendar
  log_time view_time_entries
  view_news comment_news
  view_documents
  view_wiki_pages view_wiki_edits edit_wiki_pages delete_wiki_pages
  view_messages add_messages edit_own_messages
  view_files manage_files
  browse_repository view_changesets commit_access manage_related_issues
]

TARGETS = {
  'Reporter'  => REPORTER_PERMS,
  'Developer' => DEVELOPER_PERMS,
}

puts "===== 校正前 ====="
Role.where(name: %w[Reporter Developer Manager]).order(:id).each do |r|
  puts "  #{r.name.ljust(10)} #{r.permissions.size} 项"
end
puts ""

# ---------- Reporter / Developer：覆盖成标准清单 ----------
TARGETS.each do |role_name, perms|
  role = Role.find_by(name: role_name)
  unless role
    puts "!! 找不到角色 #{role_name}，跳过"
    next
  end
  before = role.permissions.map(&:to_sym)
  added   = perms - before
  removed = before - perms
  role.permissions = perms
  role.save!
  puts "#{role_name}: #{before.size} → #{role.permissions.size} 项"
  puts "    + 补上: #{added.map(&:to_s).join(', ')}" if added.any?
  puts "    - 去掉: #{removed.map(&:to_s).join(', ')}" if removed.any?
end

# ---------- Manager（管理者）：全部权限 ----------
manager = Role.find_by(name: 'Manager')
if manager
  all = manager.setable_permissions.collect { |p| p.name }
  manager.permissions = all
  manager.save!
  puts "Manager: → #{manager.permissions.size} 项（全部）"
end

puts ""
puts "===== 校正后 ====="
Role.where(name: %w[Reporter Developer Manager]).order(:id).each do |r|
  puts "  #{r.name.ljust(10)} #{r.permissions.size} 项"
end

puts ""
puts "===== 关键权限核查（越权测试的防线）====="
def chk(role, perm)
  role.permissions.map(&:to_sym).include?(perm) ? '有' : '无'
end
r = Role.find_by(name: 'Reporter')
d = Role.find_by(name: 'Developer')
puts "  Reporter  「更新问题」(edit_issues)        : #{chk(r, :edit_issues)}   ← 必须是【无】，否则 P-01 测不出越权"
puts "  Reporter  「更新自己的问题」(edit_own_issues): #{chk(r, :edit_own_issues)}   ← 必须是【有】，S-10 才能跑"
puts "  Reporter  「删除问题」(delete_issues)      : #{chk(r, :delete_issues)}   ← 必须是【无】，否则 P-03 失效"
puts "  Reporter  「管理成员」(manage_members)     : #{chk(r, :manage_members)}   ← 必须是【无】，P-06 的前提"
puts "  Reporter  「管理版本库」(manage_repository): #{chk(r, :manage_repository)}   ← 必须是【无】，官方默认也没有"
puts "  Developer 「更新问题」(edit_issues)        : #{chk(d, :edit_issues)}   ← 必须是【有】"
puts "  Developer 「管理版本」(manage_versions)    : #{chk(d, :manage_versions)}   ← 必须是【有】，F1-10 前置"
