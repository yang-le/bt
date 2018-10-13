import asyncio
import socket
import traceback
import os


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
            if action == self.CONNECT:
                self.transport.sendto(self._annouce_request(data[8:16]))
            elif action == self.ANNOUNCE:
                interval = int.from_bytes(data[8:12], byteorder='big')
                leechers = int.from_bytes(data[12:16], byteorder='big')
                seeders = int.from_bytes(data[16:20], byteorder='big')

                peers = []
                for i in range(leechers + seeders):
                    peers.append({b'ip': bytes(socket.inet_ntoa(
                        data[20 + 6 * i:24 + 6 * i]), encoding='utf-8'), b'port': int.from_bytes(data[24 + 6 * i:26 + 6 * i], byteorder='big')})
                print(peers)
                self.transport.close()
            elif action == self.SCRAPE:
                # TODO
                pass
            elif action == self.ERROR:
                self.transport.close()
                raise ValueError(data[8:].encode('utf-8'))
            else:
                self.transport.close()
                raise ValueError('Invalid action in udp response')
        except:
            traceback.print_exc()
