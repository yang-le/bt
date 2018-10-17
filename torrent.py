import hashlib
from bencoding import encode, decode


class TorrentFile:
    def __init__(self, file):
        f = open(file, 'rb')
        data = f.read()
        f.close()

        self.__torrent = decode(data)

        self.__trackers = []
        if b'announce-list' in self.__torrent.keys():
            for l in self.__torrent[b'announce-list']:
                self.__trackers += [str(announce, 'utf-8') for announce in l]
        else:
            self.__trackers.append(str(self.__torrent[b'announce'], 'utf-8'))

        self.__info = self.__torrent[b'info']
        self.__length = 0
        if b'files' in self.__info.keys():
            for f in self.__info[b'files']:
                self.__length += f[b'length']
        else:
            self.__length = self.__info[b'length']

        self.__hash = hashlib.sha1(encode(self.__info)).digest()

    @property
    def trackers(self):
        return self.__trackers

    @property
    def length(self):
        return self.__length

    @property
    def hash(self):
        return self.__hash
    
    @property
    def name(self):
        return self.__info[b'name'].decode()
    
    @property
    def piece_length(self):
        return self.__info[b'piece_length']

    def piece_hash(self, index):
        pieces = self.__info[b'pieces']
        return pieces[20 * index:20 * (index + 1)]

    def list_files(self):
        print("%s %d" % (self.name, self.length))
        if b'files' in self.__info.keys():
            for f in self.__info[b'files']:
                path = ''
                for p in f[b'path']:
                    path += p.decode() + '/'
                print("%s %d" % (path[:-1], f[b'length']))

    def dump(self):
        print(self.__torrent)
