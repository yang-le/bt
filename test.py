import trackers
import torrent

print(trackers.get_peers(torrent.TorrentFile('test.torrent')))
