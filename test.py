import hashlib
from tornado.httpclient import HTTPClient, HTTPError
from tornado.httputil import url_concat
import os
from bencoding import encode, decode
import socket
from urllib.parse import urlparse

def peerid():
    prefix = 'yangle'.encode('utf-8')
    return prefix + os.urandom(20 - len(prefix))

f = open('test.torrent', 'rb')
data = f.read()
f.close()

data = [bytes([b]) for b in data]
torrent  = decode(data)

announces = []
if b'announce-list' in torrent.keys():
    for l in torrent[b'announce-list']:
        announces += [str(announce, 'utf-8') for announce in l]
else:
    announces.append(str(torrent[b'announce'], 'utf-8'))

info = torrent[b'info']
total_len = 0
if b'files' in info.keys():
    for f in info[b'files']:
        total_len += f[b'length']
else:
    total_len = info[b'length']

info = encode(info)
hash = hashlib.sha1(info)
#print(hash.hexdigest())
hashcode = hash.digest()

params= {
    'info_hash': hashcode,
    'peer_id': peerid(),
    'port': 6881,
    'uploaded': 0,
    'downloaded': 0,
    'left': total_len,
    'compact': 0
}

client = HTTPClient()
udp_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_client.settimeout(5)
response = None
for announce in announces:
    print('try connect ' + announce)
    url = urlparse(announce)
    if url.scheme == 'udp':
        request = []
        request += (0x41727101980).to_bytes(8, byteorder = 'big')
        request += (0).to_bytes(4, byteorder = 'big')
        transaction_id = os.urandom(4)
        request += transaction_id
        
        try:
            udp_client.sendto(bytes(request), (url.hostname, url.port))
            response = udp_client.recv(1024)
        except socket.timeout as e:
            print("Error: " + str(e))
            continue
        except Exception as e:
            # Other errors are possible, such as IOError.
            print("Error: " + str(e))
            continue

        if len(response) < 16:
            print('Invalid udp response length')
            continue

        if response[4:8] != transaction_id:
            print('Invalid transaction_id in udp response')
            continue

        action = int.from_bytes(response[0:4], byteorder = 'big')
        if action != 0:
            print('Invalid action in udp response')
            continue

        request = []
        connection_id = response[8:16]
        request += connection_id
        request += (1).to_bytes(4, byteorder = 'big') # action
        transaction_id = os.urandom(4)
        request += transaction_id
        request += hashcode
        request += peerid()
        request += (0).to_bytes(8, byteorder = 'big') # downloaded
        request += total_len.to_bytes(8, byteorder = 'big') # left
        request += (0).to_bytes(8, byteorder = 'big') # uploaded
        request += (0).to_bytes(4, byteorder = 'big') # event
        request += (0).to_bytes(4, byteorder = 'big') # ip
        request += (0).to_bytes(4, byteorder = 'big') # key
        request += (-1).to_bytes(4, byteorder = 'big', signed = True) # num_want
        request += (0).to_bytes(2, byteorder = 'big') # port
        request += b'\2'
        request += (len(url.path) + len(url.params)).to_bytes(1, byteorder = 'big') + url.path.encode() + url.params.encode()

        try:
            udp_client.sendto(bytes(request), (url.hostname, url.port))
            response = udp_client.recv(1024)
        except socket.timeout as e:
            print("Error: " + str(e))
            continue
        
        if len(response) < 20:
            print('Invalid udp response length')
            continue
        
        if response[4:8] != transaction_id:
            print('Invalid transaction_id in udp response')
            continue

        action = int.from_bytes(response[0:4], byteorder = 'big')
        if action != 1:
            print('Invalid action in udp response')
            continue
        
        interval = int.from_bytes(response[8:12], byteorder = 'big')
        leechers = int.from_bytes(response[12:16], byteorder = 'big')
        seeders = int.from_bytes(response[16:20], byteorder = 'big')

        peers = []
        for i in range(leechers + seeders):
            peers.append({'ip': int.from_bytes(response[20 + 6 * i:24 + 6 * i], byteorder = 'big'), 'port': int.from_bytes(response[24 + 6 * i:26 + 6 * i], byteorder = 'big')})

    elif url.scheme == 'http' or url.scheme == 'https':
        pass
        # try:
        #     tracker_url = url_concat(announce, params)
        #     response = client.fetch(tracker_url)
        #     break
        # except HTTPError as e:
        #     # HTTPError is raised for non-200 responses; the response
        #     # can be found in e.response.
        #     print("Error: " + str(e))
        # except Exception as e:
        #     # Other errors are possible, such as IOError.
        #     print("Error: " + str(e))

udp_client.close()
client.close()

if response:
    resdata = [bytes([b]) for b in response.body]
    res = decode(resdata)
    print(res)
