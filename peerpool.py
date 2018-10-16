import asyncio
import functools
import tracker

PeerPool = []
PeerPoolLock = asyncio.Lock()
PeerPoolSemaphore = asyncio.Semaphore(256)


async def add_peers_to_peer_pool(peers):
    if peers:
        print('pool size %d' % len(PeerPool))
        print(peers)
        async with PeerPoolLock:
            for peer in peers:
                if peer not in PeerPool:
                    PeerPool.append(peer)


def update_peer_pool(tracker_url, torrent):
    loop = asyncio.get_event_loop()

    interval, peers = loop.run_until_complete(
        tracker.get_peer_from_tracker(torrent, tracker_url, PeerPoolSemaphore))

    if not interval < 0:
        loop.call_later(interval, functools.partial(
            update_peer_pool, tracker_url, torrent))

    loop.run_until_complete(add_peers_to_peer_pool(peers))


def start_peer_pool(torrent):
    for tracker in torrent.trackers:
        update_peer_pool(tracker, torrent)
