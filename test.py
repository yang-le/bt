import peerpool
import torrent

peerpool.start_peer_pool(torrent.TorrentFile('test.torrent'))
