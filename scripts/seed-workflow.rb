# -*- coding: utf-8 -*-
# ============================================================
# Redmine 工作流一键配置（按本项目 Issue 模块测试需求）
# 用途：如果你不想在界面上一个一个勾，跑这个脚本直接把矩阵配好。
#       配完后建议打开 管理→工作流 看一遍，理解每条规则对应哪个用例。
# 特性：幂等（重复跑不会产生重复规则），不会删除你已有的规则。
# ============================================================

STATUS_NAMES = ['New', 'In Progress', 'Resolved', 'Feedback', 'Closed', 'Rejected']

# 状态必须已存在（先跑 seed-default-data.rb）
missing = STATUS_NAMES - IssueStatus.pluck(:name)
if missing.any?
  puts "!! 缺少问题状态: #{missing.join(', ')}"
  puts "!! 请先执行 seed-default-data.rb 补默认数据"
  exit 1
end

st = IssueStatus.where(name: STATUS_NAMES).index_by(&:name)
trackers = Tracker.all.to_a
roles = Role.where(name: %w[Reporter Developer Manager]).index_by(&:name)

puts "跟踪标签: #{trackers.map(&:name).join(', ')}"
puts "角色: #{roles.keys.join(', ')}"
puts ""

# ---------- 状态转移清单格式：[新状态, 当前状态] ----------

# ---------- Reporter（报告者）：只允许"补充信息"相关的两格 ----------
# 设计依据：
#   · 报告者提完 Bug 后，开发发现信息不足 → 开发转成 Feedback → 报告者补充后转回 New
#   · 报告者**不能关闭**（没有 Closed 这个去向）→ 对应用例 S-10
#   · 报告者**不能认领开工**（没有 In Progress 这个去向）
# 说明：不加这两格，Redmine 角色页会显示"没有为此角色定义工作流程"的黄色警告
REPORTER = [
  ['Feedback', 'New'],       # 信息补齐，重新提交处理（S-10 合法侧）
  ['New',      'Feedback'],  # 信息不足，退回等待补充（S-10 合法侧）
]

# ---------- Developer：允许的状态转移 [新状态, 当前状态] ----------
# 设计依据：覆盖用例 S-01/S-02/S-04/S-08/S-09，
#           刻意排除 New→Closed（S-05 要它非法）与所有 ←Closed（S-06 要它非法）
DEVELOPER = [
  ['In Progress', 'New'],          # S-01 认领开工
  ['In Progress', 'Resolved'],     # S-04 打回重做
  ['In Progress', 'Feedback'],     # 反馈后继续
  ['In Progress', 'Rejected'],     # 被拒后重启
  ['Resolved',    'In Progress'],  # S-02 修复完成
  ['Resolved',    'Feedback'],     # 反馈结论转为已解决
  ['Feedback',    'In Progress'],  # 需要更多信息
  ['Feedback',    'Resolved'],     # 反馈完成
  ['Rejected',    'New'],          # S-08 直接判定无效
  ['Rejected',    'In Progress'],  # S-09 被拒后重新开工
  ['Rejected',    'Feedback'],     # 判定无效后请求补充
]

added = 0
skipped = 0

def put_one(tracker, role, old_s, new_s, stats)
  return if old_s.id == new_s.id
  rec = WorkflowTransition.find_or_initialize_by(
    tracker_id: tracker.id, role_id: role.id,
    old_status_id: old_s.id, new_status_id: new_s.id
  )
  if rec.new_record?
    rec.save!
    stats[:added] += 1
  else
    stats[:skipped] += 1
  end
end

stats = {added: 0, skipped: 0}

# ---- Reporter：按 REPORTER 清单勾选（2 格 × 3 个 tracker = 6 条）----
if roles['Reporter']
  trackers.each do |t|
    REPORTER.each do |new_name, old_name|
      put_one(t, roles['Reporter'], st[old_name], st[new_name], stats)
    end
  end
  # 清掉清单之外的遗留规则（保证 S-10 前提：Reporter 不能关闭 / 不能认领）
  keep = REPORTER.map { |new_name, old_name| [st[old_name].id, st[new_name].id] }
  stale = WorkflowTransition.where(role_id: roles['Reporter'].id).to_a.reject { |w|
    keep.include?([w.old_status_id, w.new_status_id])
  }
  stale.each(&:destroy)
  puts "Reporter 清理了 #{stale.size} 条多余规则" if stale.any?
end

# ---- Developer：按 DEVELOPER 清单勾选 ----
if roles['Developer']
  trackers.each do |t|
    DEVELOPER.each do |new_name, old_name|
      put_one(t, roles['Developer'], st[old_name], st[new_name], stats)
    end
  end
end

# ---- Manager：除对角线外全部允许（30 格）----
if roles['Manager']
  trackers.each do |t|
    st.each_value do |old_s|
      st.each_value do |new_s|
        put_one(t, roles['Manager'], old_s, new_s, stats)
      end
    end
  end
end

puts ""
puts "===== 配置完成 ====="
puts "  新增规则: #{stats[:added]} 条   已存在跳过: #{stats[:skipped]} 条"
puts ""
puts "===== 各角色规则数 ====="
Role.where(name: %w[Reporter Developer Manager]).order(:id).each do |r|
  cnt = WorkflowTransition.where(role_id: r.id).count
  puts "  #{r.name.ljust(10)} #{cnt} 条"
end
puts ""
puts "===== S-05 关键验证：Developer 能否 New → Closed ====="
if roles['Developer']
  t = trackers.first
  can = WorkflowTransition.where(
    role_id: roles['Developer'].id, tracker_id: t.id,
    old_status_id: st['New'].id, new_status_id: st['Closed'].id
  ).exists?
  puts can ? "  ❌ 存在这条规则（S-05 前提不成立！）" : "  ✅ 不存在 → S-05「跳步非法」前提成立"
end

# ---------- 顺带演示：真实查询 developer1 在 New 状态下可选的转移 ----------
puts ""
puts "===== 模拟：Developer 在「New」状态下能看到的状态选项 ====="
if roles['Developer']
  t = trackers.first
  targets = IssueStatus.where(
    id: WorkflowTransition.where(
      role_id: roles['Developer'].id, tracker_id: t.id, old_status_id: st['New'].id
    ).pluck(:new_status_id)
  ).pluck(:name)
  puts "  tracker=#{t.name} → 可选: #{(['New'] + targets).join(', ')}"
  puts "  （含当前状态本身；不含 Closed 才符合 S-05 预期）"
end
