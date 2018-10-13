import hashlib
import os
import socket
import asyncio
import traceback
from urllib.parse import urlparse

from tornado.httpclient import HTTPClient, HTTPError
from tornado.httputil import url_concat

from bencoding import decode, encode
from trackers import UdpTrackerProtocol
from torrent import TorrentFile

def get_peers_from_http_server(url, torrent):
    client = HTTPClient()
    params = {
        'info_hash': torrent.hash,
        'peer_id': gen_peerid(),
        'port': 6881,
        'uploaded': 0,
        'downloaded': 0,
        'left': torrent.length,
        'compact': 0
    }
    tracker_url = url_concat(url.geturl(), params)
    response = client.fetch(tracker_url)
    client.close()
    resdata = decode([bytes([b]) for b in response.body])

    if b'peers' in resdata.keys():
        peers = resdata[b'peers']
        if isinstance(peers, bytes):
            ret = []
            for i in range(len(peers) // 6):
                ret.append({b'ip': bytes(socket.inet_ntoa(
                    peers[6 * i:4 + 6 * i]), encoding='utf-8'), b'port': int.from_bytes(peers[4 + 6 * i:6 + 6 * i], byteorder='big')})
                return ret
        else:
            return peers
    else:
        return []


def get_peers_from_trackers(torrent):
    response = None
    loop = asyncio.get_event_loop()
    for tracker in torrent.trackers:
        print('try connect ' + tracker)
        url = urlparse(tracker)
        try:
            if url.scheme == 'udp':
                loop.run_until_complete(loop.create_datagram_endpoint(
                    lambda: UdpTrackerProtocol(torrent), remote_addr=(url.hostname, url.port)))
            elif url.scheme == 'http' or url.scheme == 'https':
                response = get_peers_from_http_server(url, torrent)
                break
        except Exception as e:
            print("Exception: " + str(e))
    loop.close()
    return response


print(get_peers_from_trackers(TorrentFile('test.torrent')))
