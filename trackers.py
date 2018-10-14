import asyncio
import socket
import traceback
import os
from urllib.parse import urlparse


class UdpTrackerProtocol(asyncio.DatagramProtocol):
    """ UDP Tracker Protocol for BitTorrent

    see BEP 15
    """

    def __init__(self, torrent):
        self.torrent = torrent

        self.MAGIC_CONSTANT = 0x41727101980

        self.DEFAULT_PORT = 6881

        self.CONNECT = 0
        self.ANNOUNCE = 1
        self.SCRAPE = 2
        self.ERROR = 3

        # for event
        self.NONE = 0
        self.COMPLETED = 1
        self.STARTED = 2
        self.STOPPED = 3

        # see UDP Tracker Protocol Extensions
        # BEP 41
        self.END_OF_OPTIONS = 0
        self.NOP = 1
        self.URL_DATA = 2

        self.PEER_ID_PREFIX = '-YL0050-'.encode('utf-8')
        self.PEER_ID = self.PEER_ID_PREFIX + \
            os.urandom(20 - len(self.PEER_ID_PREFIX))

        self.on_finish = asyncio.get_event_loop().create_future()

    def _connection_request(self):
        request = []
        request += (self.MAGIC_CONSTANT).to_bytes(8, byteorder='big')
        request += (self.CONNECT).to_bytes(4, byteorder='big')
        self.transaction_id = os.urandom(4)
        request += self.transaction_id

        return bytes(request)

    def _annouce_request(self, connection_id, *, downloaded=0, uploaded=0, event=0, ip=0, key=0, num_wait=-1, url_data=''):
        request = []
        request += connection_id
        request += (self.ANNOUNCE).to_bytes(4, byteorder='big')  # action
        self.transaction_id = os.urandom(4)
        request += self.transaction_id
        request += self.torrent.hash
        request += self.PEER_ID
        request += (downloaded).to_bytes(8, byteorder='big')  # downloaded
        request += (self.torrent.length).to_bytes(8, byteorder='big')  # left
        request += (uploaded).to_bytes(8, byteorder='big')  # uploaded
        request += (event).to_bytes(4, byteorder='big')  # event
        request += (ip).to_bytes(4, byteorder='big')  # ip
        request += (key).to_bytes(4, byteorder='big')  # key
        request += (num_wait).to_bytes(4, byteorder='big',
                                       signed=True)  # num_want
        request += (self.DEFAULT_PORT).to_bytes(2, byteorder='big')  # port

        request += (self.URL_DATA).to_bytes(1, byteorder='big')
        request += (len(url_data)).to_bytes(1, byteorder='big')
        request += url_data.encode()

        return bytes(request)

    def _check_response(self, response):
        if (len(response) < 8):
            raise ValueError('Invalid udp response length')

        if response[4:8] != self.transaction_id:
            raise ValueError('Invalid transaction_id in udp response')

        action = int.from_bytes(response[0:4], byteorder='big')
        if action == self.CONNECT:
            if len(response) < 16:
                raise ValueError('Invalid udp response length')
        elif action == self.ANNOUNCE:
            if len(response) < 20:
                raise ValueError('Invalid udp response length')
        elif action == self.SCRAPE:
            # TODO
            pass
        elif action == self.ERROR:
            # TODO
            pass
        else:
            raise ValueError('Invalid action in udp response')

        return action

    def connection_made(self, transport):
        self.transport = transport
        self.transport.sendto(self._connection_request())

    def datagram_received(self, data, addr):
        try:
            action = self._check_response(data)
        except Exception as e:
            self.on_finish.set_exception(e)
            return

        if action == self.CONNECT:
            self.transport.sendto(self._annouce_request(data[8:16]))
            return

        if action == self.ANNOUNCE:
            interval = int.from_bytes(data[8:12], byteorder='big')
            leechers = int.from_bytes(data[12:16], byteorder='big')
            seeders = int.from_bytes(data[16:20], byteorder='big')

            peers = []
            for i in range(leechers + seeders):
                peers.append({b'ip': bytes(socket.inet_ntoa(
                    data[20 + 6 * i:24 + 6 * i]), encoding='utf-8'), b'port': int.from_bytes(data[24 + 6 * i:26 + 6 * i], byteorder='big')})
            self.on_finish.set_result(peers)
        elif action == self.SCRAPE:
            # TODO
            pass
        elif action == self.ERROR:
            self.on_finish.set_exception(ValueError(data[8:].decode('utf-8')))
        else:
            self.on_finish.set_exception(
                ValueError('Invalid action in udp response'))

    def error_received(self, exc):
        if not self.on_finish.done():
            self.on_finish.set_exception(exc)

    def connection_lost(self, exc):
        if not self.on_finish.done():
            self.on_finish.set_exception(exc)


async def get_peer_from_udp_server(torrent, url, semaphore, timeout):
    async with semaphore:
        print('try connect %s' % url.geturl())
        response = []
        transport = None
        loop = asyncio.get_event_loop()
        try:
            transport, protocol = await loop.create_datagram_endpoint(lambda: UdpTrackerProtocol(torrent), remote_addr=(url.hostname, url.port))
            response = await asyncio.wait_for(protocol.on_finish, timeout)
            # print(response)
        except Exception as e:
            print(e)
            #traceback.print_exc()
        finally:
            if transport:
                transport.close()
            return response

async def get_peers_from_udp_server(torrent, max_connection=256, timeout=None):
    semaphore = asyncio.Semaphore(max_connection)
    works = [get_peer_from_udp_server(torrent, urlparse(tracker), semaphore, timeout)
             for tracker in torrent.trackers if urlparse(tracker).scheme == 'udp']
    done, _ = await asyncio.wait(works)
    
    results = []
    for response in done:
        results += response.result()

    return results

def get_peers(torrent):
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(get_peers_from_udp_server(torrent, timeout=5))
    loop.close()

    unique = []
    for r in result:
        if r not in unique:
            unique += r

    return unique
