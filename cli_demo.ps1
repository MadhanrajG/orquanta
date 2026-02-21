write-host "🚀 OrQuanta CLI Demo Session" -ForegroundColor Cyan
write-host "--------------------------------"

# 1. Login
write-host "`n[1] Logging in..." -ForegroundColor Yellow
python orquanta_cli.py login --email cli_user@orquanta.ai --password securecli123

# 2. Status
write-host "`n[2] Checking Platform Status..." -ForegroundColor Yellow
python orquanta_cli.py status

# 3. Launch with AI
write-host "`n[3] Launching Job via AI Advisor..." -ForegroundColor Yellow
# We'll pipe 'y' to confirm the prompt since it's interactive
echo y | python orquanta_cli.py launch --description "Training a massive 500B parameter model on 10TB of text data"

# 4. List Jobs
write-host "`n[4] Listing Active Jobs..." -ForegroundColor Yellow
python orquanta_cli.py list

write-host "`n✨ Demo Complete. You can run 'python orquanta_cli.py' to use it yourself!" -ForegroundColor Green
