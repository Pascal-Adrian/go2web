import socket
import ssl

def send_http_request(host, port, request, is_https=True, timeout=15):
    """
    Send an HTTP request and return the response.
    :param host: Hostname or IP address of the server
    :param port: Port number of the server
    :param request: HTTP request string
    :param is_https: Boolean indicating if the request is HTTPS
    :param timeout: Timeout for the connection in seconds
    """

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock.settimeout(timeout)
        sock.connect((host, port))

        if is_https:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            sock = context.wrap_socket(sock, server_hostname=host)

        sock.sendall(request.encode())

        response_chunks = []
        while True:
            try:
                data = sock.recv(8192)
                if not data:
                    break
                response_chunks.append(data)
            except socket.timeout:
                print("Socket timeout while receiving data")
                break

        response = b''.join(response_chunks)

        for encoding in ['utf-8', 'latin-1', 'ascii']:
            try:
                return response.decode(encoding, errors='replace')
            except UnicodeDecodeError:
                continue

        return response.decode('latin-1', errors='replace')

    except Exception as e:
        return print(f"Error in send_http_request: {str(e)}")
    finally:
        sock.close()


if __name__ == "__main__":
    host = "jsonplaceholder.typicode.com"
    port = 443
    request = "GET /todos HTTP/1.1\r\nHost: jsonplaceholder.typicode.com\r\nConnection: close\r\n\r\n"

    res = send_http_request(host, port, request)
    print(res)
