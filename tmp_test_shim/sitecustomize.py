import socket
_ORIGINAL_GETADDRINFO = socket.getaddrinfo
_PUBLIC_HOST = 'public-example.test'
_PUBLIC_IP = '8.8.8.8'
def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == _PUBLIC_HOST:
        return [(family or socket.AF_INET, type or socket.SOCK_STREAM, proto or socket.IPPROTO_TCP, '', (_PUBLIC_IP, port))]
    return _ORIGINAL_GETADDRINFO(host, port, family, type, proto, flags)
socket.getaddrinfo = _patched_getaddrinfo
