$start = '2026-04-07T00:00:00+08:00'
$end = '2026-04-07T23:59:59+08:00'
& npx -y @larksuite/cli im +messages-search --start $start --end $end --chat-type p2p --as user --page-size 50 --format json 2>&1 | Out-File -FilePath "C:/Users/Lenovo/WorkBuddy/Claw/p2p_messages.json" -Encoding UTF8
Write-Host "单聊消息已保存到 p2p_messages.json"
