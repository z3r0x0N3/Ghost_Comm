
import socket
import threading

class Server:
    """A simple TCP server."""

    def __init__(self, host: str, port: int, handler):
        self.host = host
        self.port = port
        self.handler = handler  # Function to handle incoming data
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def start(self):
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"Server listening on {self.host}:{self.port}")

        while True:
            conn, addr = self.server_socket.accept()
            print(f"Accepted connection from {addr}")
            client_handler = threading.Thread(target=self.handle_client, args=(conn, addr))
            client_handler.start()

    def handle_client(self, conn, addr):
        with conn:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                response = self.handler(data)
                conn.sendall(response)

    def stop(self):
        self.server_socket.close()
