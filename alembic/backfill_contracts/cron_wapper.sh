#!/bin/bash
# cron_wrapper.sh
# Wrapper script for the award backfill cron job

# Set environment variables
export PYTHONPATH="/path/to/your/app:$PYTHONPATH"
export DATABASE_URL="your_database_url"
# Add other environment variables from your .env file

# Change to script directory
cd "$(dirname "$0")"

# Log file
LOG_FILE="/var/log/award_backfill_cron.log"

# Function to log with timestamp
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

log "Starting award backfill cron job"

# Run the backfill script with conservative settings for cron
python3 backfill_awards.py \
    --requests-per-day 180 \
    --output-dir /var/lib/award_backfill \
    --start-date $(date -d "1 year ago" +%Y-%m-%d) \
    --end-date $(date +%Y-%m-%d) \
    2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log "Award backfill completed successfully"
else
    log "Award backfill failed with exit code $EXIT_CODE"
fi

# Optional: Clean up old log files (keep last 30 days)
find /var/lib/award_backfill -name "*.log" -mtime +30 -delete 2>/dev/null

log "Cron job finished"

exit $EXIT_CODE

# =================
# CRONTAB ENTRIES
# =================
# 
# Add these lines to your crontab (crontab -e):
#
# Run daily at 2 AM (adjust time as needed)
# 0 2 * * * /path/to/your/scripts/cron_wrapper.sh
#
# Or run every 6 hours to spread the load:
# 0 */6 * * * /path/to/your/scripts/cron_wrapper.sh
#
# =================
# SYSTEMD TIMER ALTERNATIVE
# =================
#
# If you prefer systemd timers over cron, create these files:
#
# /etc/systemd/system/award-backfill.service:
# [Unit]
# Description=Award Backfill Service
# 
# [Service]
# Type=oneshot
# User=your_app_user
# Group=your_app_group
# WorkingDirectory=/path/to/your/app
# ExecStart=/path/to/your/scripts/cron_wrapper.sh
# Environment=PYTHONPATH=/path/to/your/app
# Environment=DATABASE_URL=your_database_url
#
# /etc/systemd/system/award-backfill.timer:
# [Unit]
# Description=Run award backfill daily
# Requires=award-backfill.service
# 
# [Timer]
# OnCalendar=daily
# Persistent=true
# 
# [Install]
# WantedBy=timers.target
#
# Then enable with:
# sudo systemctl enable award-backfill.timer
# sudo systemctl start award-backfill.timer