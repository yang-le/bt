import peerpool
import torrent
import asyncio
import tracker

pool = peerpool.PeerPool(torrent.TorrentFile('1.torrent'))
pool.start_peer_pool()
# {b'ip': b'218.193.183.215', b'port': 42176}
