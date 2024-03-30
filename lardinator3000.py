import sys
import struct

def bread(sig, data):
    return struct.unpack(f">{sig}", data)[0]

class Image:
    def __init__(self, file):
        self.file = file.read()
        self.meta = MetaData(self.read(0, 28))
        print(self.meta)
        self.iNodes = self.readIList()
        self.iMap = self.readIMap()
    
    def read(self, offset, size):
        return self.file[offset: offset + size]
    
    def readIList(self):
        data = self.read(self.meta.iListp, self.meta.iMapp - self.meta.iListp)
        res = []
        for i in range(len(data) // 32):
            offset = i * 32
            res.append(INode(data[offset: offset + 32], self.meta.iListp + offset))
        return res

    def readIMap(self):
        data = self.read(self.meta.iMapp, self.meta.dPoolp - self.meta.iMapp)
        res = []
        for i in range(len(data) // 4):
            offset = i * 4
            res.append(bread("i", data[offset: offset + 4]))
        return res

    def readDirectory(self, inode):
        file = self.readFile(inode)
        res = []
        for i in range(self.iNodes[inode].size // 32):
            res.append(DirectoryEntry(file.data[i * 32: (i + 1) * 32]))
        return res
            
    def readFile(self, inode):
        imaps = self.getImaps(inode)
        data = b""
        for map in imaps:
            data += self.read(self.meta.dPoolp + map * self.meta._ssize, self.meta._ssize)
        return FileEntry(data[:self.iNodes[inode].size])


    def getImaps(self, inode):
        res = [self.iNodes[inode].fip]
        while True:
            nv = self.iMap[res[-1]]
            if nv >= 0:
                res.append(nv)
                continue
            if nv == -1:
                print("Ran into unallocated imap while attemtping to read inode")
                exit(1)
            break
        return res


class MetaData:
    def __init__(self, data):
        self.magic = bread("8s", data[:8])
        self._ssize = bread("i", data[8:12])
        self.imageSize = bread("i", data[12:16]) * self._ssize
        self.iListp = bread("i", data[16:20]) * self._ssize
        self.iMapp = bread("i", data[20:24]) * self._ssize
        self.dPoolp = bread("i", data[24:28]) * self._ssize

    def __repr__(self):
        return " ".join(f"{k} {w}" for k,w in vars(self).items())


class INode:
    def __init__(self, data, offset):
        self.offset = offset
        modeBits = bread("h", data[:2])
        self.mode = (modeBits & 0xf000) >> 12
        self.s_ugt = (modeBits & 0x0E00) >> 9
        self.user = (modeBits & 0x01C0) >> 6
        self.group = (modeBits & 0x0038) >> 3
        self.other = modeBits & 0x0007
        self.linkCount = bread("h", data[2:4])
        self.ownerUID = bread("i", data[4:8])
        self.ownerGID = bread("i", data[8:12])
        self.cTime = bread("i", data[12:16])
        self.mTime = bread("i", data[16:20])
        self.aTime = bread("i", data[20:24])
        self.size = bread("i", data[24:28])
        self.fip = bread("i", data[28:32])

    def __repr__(self):
        return " ".join(f"{k} {w}" for k,w in vars(self).items())


class FileEntry:
    def __init__(self, data):
        self.data = data

    def __repr__(self):
        return data.decode()


class DirectoryEntry:
    def __init__(self, data):
        self.inode = bread("i", data[0:4])
        self.name = data[4:].decode()

    def __repr__(self):
        return f"({self.inode}) {self.name}"


if __name__ == "__main__":
    file = open(sys.argv[1], "rb")
    image = Image(file)
    print(image.iMap[:10])
    [print(node) for node in image.iNodes[:10]]
    print(image.readDirectory(0))
