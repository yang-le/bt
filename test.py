import hashlib
from tornado.httpclient import HTTPClient, HTTPError
from tornado.httputil import url_concat
import os
from bencoding import encode, decode
import socket
from urllib.parse import urlparse

def gen_peerid():
    prefix = 'yangle'.encode('utf-8')
    return prefix + os.urandom(20 - len(prefix))

def open_torrent(file):
    f = open(file, 'rb')
    data = f.read()
    f.close()

    data = [bytes([b]) for b in data]
    torrent  = decode(data)
    return torrent

def get_torrent_announces(torrent):
    announces = []
    if b'announce-list' in torrent.keys():
        for l in torrent[b'announce-list']:
            announces += [str(announce, 'utf-8') for announce in l]
    else:
        announces.append(str(torrent[b'announce'], 'utf-8'))
    return announces

def get_torrent_length(torrent):
    info = torrent[b'info']
    total_len = 0
    if b'files' in info.keys():
        for f in info[b'files']:
            total_len += f[b'length']
    else:
        total_len = info[b'length']
    return total_len

def get_torrent_hash(torrent):
    info = torrent[b'info'] 
    info = encode(info)
    hash = hashlib.sha1(info)
    #print(hash.hexdigest())
    hashcode = hash.digest()
    return hashcode

def get_peers_from_udp_server(url, torrent):
    request = []
    request += (0x41727101980).to_bytes(8, byteorder = 'big')
    request += (0).to_bytes(4, byteorder = 'big')
    transaction_id = os.urandom(4)
    request += transaction_id

    udp_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_client.settimeout(5)    
    udp_client.sendto(bytes(request), (url.hostname, url.port))
    response = udp_client.recv(1024)
    udp_client.close()
    
    if len(response) < 16:
        raise ValueError('Invalid udp response length')

    if response[4:8] != transaction_id:
        raise ValueError('Invalid transaction_id in udp response')

    action = int.from_bytes(response[0:4], byteorder = 'big')
    if action != 0:
        raise ValueError('Invalid action in udp response')

    request = []
    connection_id = response[8:16]
    request += connection_id
    request += (1).to_bytes(4, byteorder = 'big') # action
    transaction_id = os.urandom(4)
    request += transaction_id
    request += get_torrent_hash(torrent)
    request += gen_peerid()
    request += (0).to_bytes(8, byteorder = 'big') # downloaded
    request += get_torrent_length(torrent).to_bytes(8, byteorder = 'big') # left
    request += (0).to_bytes(8, byteorder = 'big') # uploaded
    request += (0).to_bytes(4, byteorder = 'big') # event
    request += (0).to_bytes(4, byteorder = 'big') # ip
    request += (0).to_bytes(4, byteorder = 'big') # key
    request += (-1).to_bytes(4, byteorder = 'big', signed = True) # num_want
    request += (0).to_bytes(2, byteorder = 'big') # port
    request += b'\2'
    request += (len(url.path) + len(url.params)).to_bytes(1, byteorder = 'big') + url.path.encode() + url.params.encode()

    udp_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_client.settimeout(5)    
    udp_client.sendto(bytes(request), (url.hostname, url.port))
    response = udp_client.recv(1024)
    udp_client.close()
    
    if len(response) < 20:
        raise ValueError('Invalid udp response length')
    
    if response[4:8] != transaction_id:
        raise ValueError('Invalid transaction_id in udp response')

    action = int.from_bytes(response[0:4], byteorder = 'big')
    if action != 1:
        raise ValueError('Invalid action in udp response')
    
    interval = int.from_bytes(response[8:12], byteorder = 'big')
    leechers = int.from_bytes(response[12:16], byteorder = 'big')
    seeders = int.from_bytes(response[16:20], byteorder = 'big')

    peers = []
    for i in range(leechers + seeders):
        peers.append({b'ip': bytes(socket.inet_ntoa(response[20 + 6 * i:24 + 6 * i]), encoding = 'utf-8'), b'port': int.from_bytes(response[24 + 6 * i:26 + 6 * i], byteorder = 'big')})
    return peers

def get_peers_from_http_server(url, torrent):
    client = HTTPClient()
    params= {
        'info_hash': get_torrent_hash(torrent),
        'peer_id': gen_peerid(),
        'port': 6881,
        'uploaded': 0,
        'downloaded': 0,
        'left': get_torrent_length(torrent),
        'compact': 0
    }
    tracker_url = url_concat(url.geturl(), params)
    response = client.fetch(tracker_url)
    client.close()
    resdata = [bytes([b]) for b in response.body]
    return decode(resdata)[b'peers']

def get_peers_from_trackers(torrent):
    response = None
    for tracker in get_torrent_announces(torrent):
        print('try connect ' + tracker)
        url = urlparse(tracker)
        try:
            if url.scheme == 'udp':
                response = get_peers_from_udp_server(url, torrent)
                break
            elif url.scheme == 'http' or url.scheme == 'https':
                response = get_peers_from_http_server(url, torrent)
                break
        except Exception as e:
            print("Exception: " + str(e))
    return response

print(get_peers_from_trackers(open_torrent('test.torrent')))
