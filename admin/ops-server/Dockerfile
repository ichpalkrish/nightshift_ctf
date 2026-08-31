FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

# ---- base packages ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    php-cli \
    python3 python3-pip \
    wget curl \
    gcc make libpam-dev libssl-dev \
    libcap2-bin \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --break-system-packages pyftpdlib

# ---- pinned VULNERABLE sudo (CVE-2025-32463) ----
# dpkg -i will fail with unmet deps (libapparmor1 etc.) — that's expected.
# apt-get install -f then resolves ALL missing deps and completes the install.
# apt-mark hold prevents any later upgrade from silently patching it.
COPY sudo_vuln.deb /tmp/sudo_vuln.deb
RUN apt-get update \
    && dpkg -i /tmp/sudo_vuln.deb; \
       apt-get install -f -y; \
       apt-mark hold sudo; \
       rm -f /tmp/sudo_vuln.deb \
    && rm -rf /var/lib/apt/lists/* \
    && sudo --version | head -1

# ---- alt privesc path: capability misconfiguration ----
RUN setcap cap_setuid+ep $(readlink -f $(which python3))

# ---- users ----
# www-data runs the PHP server so any uploaded webshell lands as low-priv
RUN useradd -r -m -s /usr/sbin/nologin www-data 2>/dev/null || true

# ---- application layout ----
RUN mkdir -p /var/www/html/files /var/www/html/uploads
COPY files/ /var/www/html/files/
RUN chmod -R go+r /var/www/html/files && find /var/www/html/files -type d -exec chmod 755 {} \;
RUN chown -R www-data:www-data /var/www/html/uploads && chmod 755 /var/www/html/uploads

COPY ftp_server.py /opt/ftp_server.py
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

# ---- filesystem pollution (decoys + one fake flag, NOT root-only) ----
COPY fs-overlay/var/www/system.log /var/www/system.log
COPY fs-overlay/var/www/.env /var/www/.env
COPY fs-overlay/home/www-data/.bash_history /home/www-data/.bash_history
COPY fs-overlay/home/www-data/notes.txt /home/www-data/notes.txt
COPY fs-overlay/opt/nightshift-agent/ /opt/nightshift-agent/
COPY fs-overlay/etc/cron.d/agent-sync /etc/cron.d/agent-sync
RUN chown -R www-data:www-data /home/www-data

# ---- root-only files: the sealed flag + a final lore note ----
COPY fs-overlay/root/flag.enc /root/flag.enc
COPY fs-overlay/root/.last_entry /root/.last_entry
RUN chmod 600 /root/flag.enc /root/.last_entry && chown root:root /root/flag.enc /root/.last_entry

EXPOSE 21 8080
EXPOSE 30000-30009

CMD ["/opt/entrypoint.sh"]
