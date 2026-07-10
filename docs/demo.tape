Set Theme "Monokai Pro"
Set FontSize 18
Set Width 1000
Set Height 560

Hide
Type "echo '# ContextLedger — Git for AI memory'"
Enter
Sleep 500ms
Type "clear"
Enter
Sleep 500ms
Show

Type "echo '# 1/7  Create a local memory vault'"
Enter
Sleep 500ms
Type "memory init /tmp/contextledger-demo"
Enter
Sleep 1.5s

Type "echo '# 2/7  Capture source notes'"
Enter
Sleep 500ms
Type "memory --vault /tmp/contextledger-demo capture file /tmp/demo-source.md"
Enter
Sleep 1.5s

Type "echo '# 3/7  Process into linked knowledge'"
Enter
Sleep 500ms
Type "memory --vault /tmp/contextledger-demo process"
Enter
Sleep 1.5s

Type "echo '# 4/7  Index into SQLite + FTS5'"
Enter
Sleep 500ms
Type "memory --vault /tmp/contextledger-demo index --apply"
Enter
Sleep 1.5s

Type "echo '# 5/7  Search with BM25 scores'"
Enter
Sleep 500ms
Type "memory --vault /tmp/contextledger-demo search 'memory systems'"
Enter
Sleep 1.5s

Type "echo '# 6/7  Check graph health'"
Enter
Sleep 500ms
Type "memory --vault /tmp/contextledger-demo health"
Enter
Sleep 1.5s

Type "echo '# 7/7  Diagnose vault issues'"
Enter
Sleep 500ms
Type "memory --vault /tmp/contextledger-demo doctor"
Enter
Sleep 2s
