import json
import re
import socket
import ssl
import time
from urllib.parse import urlparse, quote_plus, unquote
import os
from bs4 import BeautifulSoup
import argparse

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
CACHE_DIR = ".cache"
CACHE_EXPIRATION = 60 * 60


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


def cache_response(url, status_code, headers, body):
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

    cache_key = re.sub(r'[^a-zA-Z0-9]', '_', url)

    if len(cache_key) > 255:
        cache_key = cache_key[:255]

    cache_file = os.path.join(CACHE_DIR, cache_key)

    cache_data = {
        "timestamp": time.time(),
        "status_code": status_code,
        "headers": headers,
        "body": body
    }

    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False)
    except Exception as e:
        print(f"Error writing to cache file {cache_file}: {str(e)}")


def get_cached_response(url):
    """
    Retrieve cached response for the given URL.
    :param url: URL to search in the cache
    :return: status_code, headers, body if found, else None
    """
    if not os.path.exists(CACHE_DIR):
        return None

    cache_key = re.sub(r'[^a-zA-Z0-9]', '_', url)

    if len(cache_key) > 255:
        cache_key = cache_key[:255]

    cache_file = os.path.join(CACHE_DIR, cache_key)

    if not os.path.exists(cache_file):
        return None

    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)

            if time.time() - cache_data["timestamp"] > CACHE_EXPIRATION:
                os.remove(cache_file)
                return None

            return cache_data
    except Exception as e:
        print(f"Error reading from cache file {cache_file}: {str(e)}")
        return None


def fetch_url(url, max_redirects=10, cache=True):
    """
    Perform a GET request to the specified URL.
    :param url: URL to fetch
    :param max_redirects: Maximum number of redirects to follow
    :param cache: Boolean indicating if caching is enabled
    """
    redirect_count = 0
    visited_urls = {url}
    redirect_url = url

    status_code, headers, body = None, None, None

    if cache:
        cached_response = get_cached_response(url)
        if cached_response:
            print(f"Using cached response for {url}...")
            return cached_response["status_code"], cached_response["headers"], cached_response["body"]

    while redirect_count < max_redirects:
        host, path, protocol, port = parse_url(redirect_url)
        request = create_http_request(host, path=path)
        response = send_http_request(host, port, request)
        status_code, headers, body = parse_response(response)

        if status_code.startswith("3"):
            location = headers.get("Location")

            if not location:
                return status_code, headers, body

            if location.startswith("http"):
                redirect_url = location
            elif location.startswith("//"):
                redirect_url = protocol + ":" + location
            elif location.startswith("/"):
                redirect_url = protocol + "://" + host + location
            else:
                redirect_url = protocol + "://" + host + "/" + location

            if redirect_url in visited_urls:
                print(f"Redirect loop detected: {url} -> {redirect_url}")
                break

            print(f"Redirecting to: {redirect_url} ...")
            visited_urls.add(redirect_url)
            redirect_count += 1
        else:
            if cache:
                cache_response(url, status_code, headers, body)

            return status_code, headers, body

    if redirect_count >= max_redirects:
        print(f"Max redirects reached for {url}")

    return status_code, headers, body


def extract_seo_information(html_body):
    """
    Extract SEO information from the HTML body.
    :param html_body: HTML body of the response
    :return:
    """

    seo_info = {
        "title": None,
        "description": None,
        "keywords": None,
        "h1_tags": [],
        "canonical": None,
        "robots": None,
        "og_title": None,
        "og_description": None,
        "og_image": None,
        "twitter_card": None,
        "twitter_title": None,
        "twitter_description": None,
        "twitter_image": None
    }

    try:
        soup = BeautifulSoup(html_body, 'html.parser')

        title_tag = soup.find('title')
        if title_tag:
            seo_info["title"] = title_tag.get_text(strip=True)

        for meta_tag in soup.find_all('meta'):
            name = meta_tag.get('name', '').lower()
            property = meta_tag.get('property', '').lower()
            content = meta_tag.get('content', '').strip()

            if name in seo_info.keys():
                seo_info[name] = content
            elif property in seo_info.keys():
                seo_info[property] = content

        for h1_tag in soup.find_all('h1'):
            seo_info["h1_tags"].append(h1_tag.get_text(strip=True))

        canonical_tag = soup.find('link', rel='canonical')
        if canonical_tag:
            seo_info["canonical"] = canonical_tag.get('href', '').strip()

        return seo_info

    except Exception as e:
        print(f"Error parsing HTML: {str(e)}")
        return seo_info


def parse_html_body(html_body):
    """
    Parse the HTML body and extract useful information.
    :param html_body: HTML body of the response
    :return: Parsed HTML body
    """
    try:
        soup = BeautifulSoup(html_body, 'html.parser')

        for script in soup(['script', 'style']):
            script.extract()

        text = soup.find('body').get_text()

        lines = (line.strip() for line in text.splitlines())

        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))

        text = '\n'.join(chunk for chunk in chunks if chunk)

        return text

    except Exception as e:
        print(f"Error parsing HTML body: {str(e)}")
        return html_body


def parse_json_body(json_body):
    """
    Parse the JSON body and extract useful information.
    :param json_body: JSON body of the response
    :return: Parsed JSON body
    """
    try:
        parsed_json = json.loads(json_body)
        return json.dumps(parsed_json, indent=4)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON body: {str(e)}")
        return json_body


def search_duckduckgo(query, max_results=10):
    """
    Search DuckDuckGo for a given query and return the results.
    :param query: Search query
    :param max_results: Maximum number of results to return
    :return: List of search results
    """

    encoded_query = quote_plus(query)

    search_url = f"https://duckduckgo.com/html/?q={encoded_query}"

    status_code, headers, body = fetch_url(search_url)

    if not body:
        print("Error fetching search results")
        return []

    if not status_code.startswith("2"):
        print(f"Error: Received status code {status_code}")
        return []

    try:
        soup = BeautifulSoup(body, 'html.parser')

        results = []

        results_containers = soup.select('.results_links') or soup.select('.result')

        for container in results_containers:
            title_elem = (container.select_one('.result__title a') or
                     container.select_one('.result__a') or
                     container.select_one('a.result__url') or
                     container.select_one('h2 a'))

            if title_elem:
                title = title_elem.get_text().strip()
                href = title_elem.get('href', '')

                # Extract URL from DuckDuckGo redirect format
                if href:
                    # Try to find the URL in the "uddg" parameter
                    match = re.search(r'uddg=([^&]+)', href)
                    if match:
                        url = unquote(match.group(1))
                        results.append({'title': title, 'url': url})
                    else:
                        # Use the href directly if it looks like a URL
                        if href.startswith(('http://', 'https://')):
                            results.append({'title': title, 'url': href})

        if not results:
            for link in soup.find_all('a'):
                href = link.get('href', '')
                if 'uddg=' in href:
                    title = link.get_text().strip()
                    match = re.search(r'uddg=([^&]+)', href)
                    if match and title:
                        url = unquote(match.group(1))
                        results.append({'title': title, 'url': url})

        print(f"Found {len(results)} results")

        return results[:max_results]

    except Exception as e:
        print(f"Error parsing search results: {str(e)}")
        return []


def handle_url_command(url):
    """
    Handle the URL command and fetch the URL.
    :param url: URL to fetch
    :return: None
    """

    try:
        status_code, headers, body = fetch_url(url)
        if status_code.startswith("2"):
            content_type = headers.get("Content-Type", "")
            if "application/json" in content_type:
                parsed_body = parse_json_body(body)
                print("=" * 50)
                print("JSON Response:")
                print("=" * 50)
                print(parsed_body)
                print("=" * 50)
            elif "text/html" in content_type:
                parsed_body = parse_html_body(body)
                seo_info = extract_seo_information(body)
                print("=" * 50)
                print("HTML Response:")
                print("=" * 50)
                print("\nSEO Information:")
                print("-" * 50)
                print(f"Title: {seo_info['title']}")
                print(f"Description: {seo_info['description']}")
                print(f"Keywords: {seo_info['keywords']}")
                print(f"Canonical: {seo_info['canonical']}")
                print(f"Robots: {seo_info['robots']}")

                print("\nOpen Graph:")
                print(f"OG Title: {seo_info['og_title']}")
                print(f"OG Description: {seo_info['og_description']}")
                print(f"OG Image: {seo_info['og_image']}")

                print("\nTwitter Card:")
                print(f"Twitter Card: {seo_info['twitter_card']}")
                print(f"Twitter Title: {seo_info['twitter_title']}")
                print(f"Twitter Description: {seo_info['twitter_description']}")
                print(f"Twitter Image: {seo_info['twitter_image']}")

                print("\nH1 Tags:")
                for i, h1 in enumerate(seo_info.get('h1_tags', []), 1):
                    print(f"{i}. {h1}")

                print("-" * 50)
                print("\nParsed Body:")
                print("-" * 50)
                print(parsed_body)
                print("=" * 50)
            else:
                print(f"Response Body:\n{body}")

        else:
            print(f"Error fetching URL: {status_code}")

    except Exception as e:
        print(e)


def handle_search_command(query):
    """
    Handle the search command and fetch results from DuckDuckGo.
    :param query: Search query
    :return: None
    """

    results = search_duckduckgo(query)

    if results:
        print("=" * 50)
        print("Search Results:")
        print("=" * 50)
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['title']}")
            print(f"   URL: {result['url']}")
            print("-" * 50)
        print("=" * 50)
    else:
        print("No results found.")


def main():
    """
    Main function to handle command line arguments and execute the appropriate command.
    :return:
    """
    parser = argparse.ArgumentParser(description="go2web - A CLI tool for HTTP requests and web searches")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("-u", "--url", help="Make an HTTP request to the specified URL and print the response")
    group.add_argument("-s", "--search", help="Search the term using DuckDuckGo and print top 10 results", nargs='+')

    args = parser.parse_args()

    if args.url:
        handle_url_command(args.url)
    elif args.search:
        search_term = " ".join(args.search)
        handle_search_command(search_term)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
