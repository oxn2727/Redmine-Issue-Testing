# 清理接口探测/测试过程中产生的 Issue，让环境回到干净状态
# 说明：这些数据都是自动化探测和测试跑出来的，用户执行用例时应当从零开始
before = Issue.count
Issue.find_each(&:destroy)
after = Issue.count

puts "清理前 Issue 数：#{before}"
puts "清理后 Issue 数：#{after}"
puts ""
puts "剩余关联数据："
puts "  journals  : #{Journal.count}"
puts "  time_entries: #{TimeEntry.count}"
puts "  附件      : #{Attachment.where(container_type: 'Issue').count}"
