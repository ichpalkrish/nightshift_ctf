#!/bin/bash
# FTP needs root to bind :21 and the passive range.
python3 /opt/ftp_server.py &

# PHP serves as low-priv www-data — this is the critical bit.
# If this ran as root, there would be no privesc stage at all.
su -s /bin/bash www-data -c "php -S 0.0.0.0:8080 -t /var/www/html" &

wait -n
