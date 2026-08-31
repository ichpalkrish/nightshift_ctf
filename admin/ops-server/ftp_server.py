"""
FTP service for the ops-server. svcbackup is jailed to /var/www/html/uploads —
it cannot read /var/www/html/files (that must stay SSRF-only).
"""
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

UPLOADS_DIR = "/var/www/html/uploads"

authorizer = DummyAuthorizer()
# home dir = uploads only. pyftpdlib jails the session to this path —
# the user has no protocol-level way to cd above it.
authorizer.add_user("svcbackup", "Backup$2024!", UPLOADS_DIR, perm="elradfmwMT")

handler = FTPHandler
handler.authorizer = authorizer
handler.banner = "Nightshift FTP ready"

# passive port range — must be published in docker-compose
handler.passive_ports = range(30000, 30010)

server = FTPServer(("0.0.0.0", 21), handler)
server.serve_forever()
