# Статичен сървър за пакета. Стандартният http.server има опашка 5 и на Windows отказва връзки при вълна от заявки.
import sys, functools
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
class S(ThreadingHTTPServer):
    request_queue_size = 512; daemon_threads = True
class H(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
S(("0.0.0.0", int(sys.argv[2])), functools.partial(H, directory=sys.argv[1])).serve_forever()
