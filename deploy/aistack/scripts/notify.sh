#!/bin/bash
# Уведомление владельцу в Telegram
set -a; . /home/goga/.ouroboros.env; set +a
curl -s -m 15 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" -d chat_id=509331449 --data-urlencode "text=⚠️ $(hostname): $*" >/dev/null
