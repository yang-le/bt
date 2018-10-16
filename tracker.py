import asyncio
import socket
import traceback
import os
import aiohttp
import urllib.parse
import bencoding


DEFAULT_PORT = 6881
PEER_ID_PREFIX = '-YL0050-'.encode('utf-8')
PEER_ID = PEER_ID_PREFIX + os.urandom(20 - len(PEER_ID_PREFIX))


class UdpTrackerProtocol(asyncio.DatagramProtocol):
    """ UDP Tracker Protocol for BitTorrent

    see BEP 15
    """

    def __init__(self, torrent):
        self.torrent = torrent

        self.MAGIC_CONSTANT = 0x41727101980

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
        request += PEER_ID
        request += (downloaded).to_bytes(8, byteorder='big')  # downloaded
        request += (self.torrent.length).to_bytes(8, byteorder='big')  # left
        request += (uploaded).to_bytes(8, byteorder='big')  # uploaded
        request += (event).to_bytes(4, byteorder='big')  # event
        request += (ip).to_bytes(4, byteorder='big')  # ip
        request += (key).to_bytes(4, byteorder='big')  # key
        request += (num_wait).to_bytes(4, byteorder='big',
                                       signed=True)  # num_want
        request += (DEFAULT_PORT).to_bytes(2, byteorder='big')  # port

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
            # TODO support interval
            interval = int.from_bytes(data[8:12], byteorder='big')
            leechers = int.from_bytes(data[12:16], byteorder='big')
            seeders = int.from_bytes(data[16:20], byteorder='big')

            peers = []
            for i in range(leechers + seeders):
                peers.append({b'ip': bytes(socket.inet_ntoa(
                    data[20 + 6 * i:24 + 6 * i]), encoding='utf-8'), b'port': int.from_bytes(data[24 + 6 * i:26 + 6 * i], byteorder='big')})
            self.on_finish.set_result((interval, peers))
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


async def get_peer_from_http_server(torrent, url, semaphore, timeout):
    async with semaphore:
        print('try connect %s' % url)
        response = None
        params = {
            'info_hash': urllib.parse.quote_from_bytes(torrent.hash),
            'peer_id': urllib.parse.quote_from_bytes(PEER_ID),
            'port': DEFAULT_PORT,
            'uploaded': 0,
            'downloaded': 0,
            'left': torrent.length,
        }
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.get(url, params=params) as resp:
                    response = await resp.read()
        except Exception as e:
            print(e)
            # traceback.print_exc()
        finally:
            interval = -1
            peers = []

            resdata = {}
            if (response):
                try:
                    resdata = bencoding.decode(response)
                except Exception as e:
                    print(e)

            if b'failure reason' in resdata.keys():
                print(resdata[b'failure reason'])

            if b'interval' in resdata.keys():
                interval = resdata[b'interval']

            if b'peers' in resdata.keys():
                peer_list = resdata[b'peers']
                if isinstance(peer_list, bytes):
                    for i in range(len(peer_list) // 6):
                        peers.append({b'ip': bytes(socket.inet_ntoa(
                            peer_list[6 * i:4 + 6 * i]), encoding='utf-8'), b'port': int.from_bytes(peer_list[4 + 6 * i:6 + 6 * i], byteorder='big')})
                else:
                    peers = peer_list
            return interval, peers


async def get_peer_from_udp_server(torrent, url, semaphore, timeout):
    async with semaphore:
        print('try connect %s' % url.geturl())
        interval = -1
        peers = []
        transport = None
        loop = asyncio.get_event_loop()
        try:
            transport, protocol = await loop.create_datagram_endpoint(lambda: UdpTrackerProtocol(torrent), remote_addr=(url.hostname, url.port))
            interval, peers = await asyncio.wait_for(protocol.on_finish, timeout)
            # print(response)
        except Exception as e:
            print(e)
            # traceback.print_exc()
        finally:
            if transport:
                transport.close()
            return interval, peers


async def get_peer_from_tracker(torrent, url, semaphore):
    tracker_url = urllib.parse.urlparse(url)
    if tracker_url.scheme == 'udp':
        return await get_peer_from_udp_server(torrent, tracker_url, semaphore, 5)
    if tracker_url.scheme == 'http' or tracker_url.scheme == 'https':
        return await get_peer_from_http_server(torrent, url, semaphore, 10)
    return -1, []
