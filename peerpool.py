import asyncio
import functools
import tracker

class PeerPool:

    def __init__(self, torrent):
        self.pool = []
        self.torrent = torrent
        self.__lock = asyncio.Lock()
        self.__sem = asyncio.Semaphore(256)

    async def init_peer_protocol(self, url, port):
        reader, writer = await asyncio.open_connection(url, port)
        
        handshake = []
        handshake += (19).to_bytes(1, byteorder='big')
        handshake += b'BitTorrent protocol'
        handshake += (0).to_bytes(8, byteorder='big')
        handshake += self.torrent.hash
        handshake += tracker.PEER_ID

        writer.write(bytes(handshake))
        await writer.drain()

        data = await reader.read()
        print(data)

        writer.close()

    async def add_peers_to_peer_pool(self, peers):
        print('pool size %d' % len(self.pool))
        print(peers)
        works = []
        async with self.__lock:
            for peer in peers:
                if peer not in self.pool:
                    self.pool.append(peer)
                    works.append(self.init_peer_protocol(peer[b'ip'].decode(), peer[b'port']))
        try:
            done, _ = await asyncio.wait(works)
            for d in done:
                print(d.exception())
        except Exception as e:
            print(e)

    def update_peer_pool(self, tracker_url):
        loop = asyncio.get_event_loop()

        interval, peers = loop.run_until_complete(
            tracker.get_peer_from_tracker(self.torrent, tracker_url, self.__sem))

        if not interval < 0:
            loop.call_later(interval, functools.partial(
                self.update_peer_pool, self, tracker_url, self.torrent))
        if peers:
            loop.run_until_complete(self.add_peers_to_peer_pool(peers))


    def start_peer_pool(self):
        for tracker in self.torrent.trackers:
            self.update_peer_pool(tracker)
        loop = asyncio.get_event_loop()
        loop.run_forever()
