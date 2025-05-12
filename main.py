import socket
import ssl
from urllib.parse import urlparse

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")


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


def create_http_request(host, method="GET", path="/", headers=None, body=None):
    """
    Create an HTTP request string.
    :param host: Hostname or IP address of the server
    :param method: HTTP method (GET, POST, etc.)
    :param path: Path of the resource
    :param headers: Dictionary of HTTP headers
    :param body: Request body for POST/PUT requests
    """
    if headers is None:
        headers = {}

    headers.update({
        "Host": host,
        "User-Agent": USER_AGENT,  # User-Agent header to minimize blocking
        "Accept": "text/html,application/json,*/*",
        "Accept-Encoding": "identity",
        "Connection": "close"
    })

    request_line = f"{method} {path} HTTP/1.1\r\n"
    header_lines = ''.join(f"{key}: {value}\r\n" for key, value in headers.items())

    request = request_line + header_lines + "\r\n"

    if body:
        headers["Content-Length"] = str(len(body))
        request += body

    return request


def parse_url(url):
    """Parse URL into components."""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    parsed_url = urlparse(url)
    host = parsed_url.netloc
    path = parsed_url.path if parsed_url.path else "/"
    query = parsed_url.query

    if query:
        path = path + "?" + query

    protocol = parsed_url.scheme

    port = 443 if protocol == "https" else 80

    return host, path, protocol, port


def process_headers(headers):
    """
    Process HTTP headers into a dictionary.
    :param headers: HTTP headers string
    """
    header_lines = headers.split("\r\n")
    header_dict = {}

    for line in header_lines:
        if ":" in line:
            key, value = line.split(":", 1)
            header_dict[key.strip()] = value.strip() if value else ""
        elif line.startswith("HTTP/"):
            parts = line.split(" ", 2)
            if len(parts) > 2:
                header_dict["Status"] = parts[1] + " " + parts[2]
            else:
                header_dict["Status"] = parts[1]

    return header_dict


def decode_chunked_response(body):
    """
    Decode chunked HTTP response body (after headers have been removed).
    :param body: Chunked HTTP response body (without headers)
    :return: Decoded response body
    """
    decoded = ""
    index = 0

    while index < len(body):
        chunk_size_end = body.find("\r\n", index)
        if chunk_size_end == -1:
            decoded += body[index:]
            break

        try:
            chunk_size_line = body[index:chunk_size_end].strip()
            if ";" in chunk_size_line:
                chunk_size_line = chunk_size_line.split(";")[0]
            chunk_size = int(chunk_size_line, 16)
        except (ValueError, IndexError):
            decoded += body[index:]
            break

        if chunk_size == 0:
            break

        chunk_start = chunk_size_end + 2
        chunk_end = chunk_start + chunk_size

        if chunk_end <= len(body):
            decoded += body[chunk_start:chunk_end]
            index = chunk_end + 2
        else:
            decoded += body[chunk_start:]
            break

    return decoded


def parse_response(response):
    """
    Parse the HTTP response.
    :param response: HTTP response string
    """
    headers, body = response.split("\r\n\r\n", 1)
    headers = process_headers(headers)
    status_code = headers.get("Status", "").split(" ")[0]
    if "Transfer-Encoding" in headers and headers["Transfer-Encoding"].lower() == "chunked":
        body = decode_chunked_response(body)

    return status_code, headers, body


def fetch_url(url):
    """
    Perform a GET request to the specified URL.
    :param url: URL to fetch
    """
    host, path, protocol, port = parse_url(url)
    request = create_http_request(host, path=path)
    response = send_http_request(host, port, request)
    status_code, headers, body = parse_response(response)

    return status_code, headers, body


if __name__ == "__main__":
    url = "https://en.wikipedia.org/wiki/Main_Page"
    response = fetch_url(url)
    status_code, headers, body = parse_response(response)
    print(body)
