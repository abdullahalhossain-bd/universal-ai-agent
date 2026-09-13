import socket
_ORIGINAL_GETADDRINFO = socket.getaddrinfo
_ORIGINAL_CREATE_CONNECTION = socket.create_connection
_ORIGINAL_SOCKET_CONNECT = socket.socket.connect
_PUBLIC_HOST = 'public-example.test'
_PUBLIC_IPS = {'8.8.8.8', '93.184.216.34'}
def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == _PUBLIC_HOST:
        return [(family or socket.AF_INET, type or socket.SOCK_STREAM, proto or socket.IPPROTO_TCP, '', ('8.8.8.8', port))]
    return _ORIGINAL_GETADDRINFO(host, port, family, type, proto, flags)
def _patched_create_connection(address, *args, **kwargs):
    if isinstance(address, tuple) and len(address) >= 2 and address[0] in _PUBLIC_IPS:
        address = ('127.0.0.1', address[1])
    return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)
def _patched_socket_connect(self, address, *args, **kwargs):
    if isinstance(address, tuple) and len(address) >= 2 and address[0] in _PUBLIC_IPS:
        address = ('127.0.0.1', address[1])
    return _ORIGINAL_SOCKET_CONNECT(self, address, *args, **kwargs)
socket.getaddrinfo = _patched_getaddrinfo
socket.create_connection = _patched_create_connection
socket.socket.connect = _patched_socket_connect
