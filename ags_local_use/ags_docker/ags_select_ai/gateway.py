"""Loopback access to two fixed services on Docker's otherwise internal network."""
import socket
import socketserver
import threading


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        upstream = socket.create_connection(self.server.destination, timeout=10)
        upstream.settimeout(None)

        def copy(source, target):
            try:
                while data := source.recv(65536):
                    target.sendall(data)
            except OSError:
                pass
            finally:
                try:
                    target.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        thread = threading.Thread(target=copy, args=(self.request, upstream), daemon=True)
        thread.start()
        copy(upstream, self.request)
        thread.join(timeout=5)
        upstream.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    for port, destination in [(1521, ('oracle', 1521)), (8080, ('adapter', 8080))]:
        server = Server(('0.0.0.0', port), Relay)
        server.destination = destination
        threading.Thread(target=server.serve_forever, daemon=False).start()
