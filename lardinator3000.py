import sys
import struct

def bread(fmt, data):
    """Takes a struct format string and data to read from to return the interpreted data"""
    return struct.unpack(f">{fmt}", data)[0]

class Image:
    """
    Holds the data and in memory portions of file. Also holds 
    all of the functions to interact with the file system.
    """
    def __init__(self, filename):
        self.filename = filename
        self.meta = MetaData(open(self.filename, "rb").read()[:28])
        print(self.meta)
        self.iNodes = self.readIList()
        self.iMap = self.readIMap()
    
    def read(self, offset):
        """Reads size bytes from offset in the file."""
        file = open(self.filename, "rb")
        data = file.read()[offset: offset + self.meta._ssize]
        file.close()
        return data
    
    def readIList(self):
        """Reads in INodes from IList and stores them in memory."""
        size = self.meta.iMapp - self.meta.iListp
        data = b""
        amountRead = 0
        while size - amountRead > 0:
            data += self.read(self.meta.iListp + amountRead)
            amountRead += self.meta._ssize
        data = data[:size]
        res = []
        for i in range(len(data) // 32): # Each i-node is 32 bytes in length
            offset = i * 32
            res.append(INode(data[offset: offset + 32], self.meta.iListp + offset)) # Keep track of offset for writing later
        return res

    def readIMap(self):
        """Reads in all IMap entries into memory."""
        size = self.meta.dPoolp - self.meta.iMapp
        data = b""
        amountRead = 0
        while size - amountRead > 0:
            data += self.read(self.meta.iMapp + amountRead)
            amountRead += self.meta._ssize
        data = data[:size]
        res = []
        for i in range(len(data) // 4):
            offset = i * 4
            res.append(bread("i", data[offset: offset + 4]))
        return res

    def readSector(self, imap):
        return self.read(self.meta.dPoolp + imap * self.meta._ssize)

    def readDirectory(self, inode):
        file = self.readFile(inode)
        res = []
        for i in range(self.iNodes[inode].size // 32):
            res.append(DirectoryEntry(file.data[i * 32: (i + 1) * 32]))
        return res
            
    def readFile(self, inode):
        imaps = self.getImaps(inode)
        data = b""
        for index in imaps:
            data += self.readSector(index)
        return FileEntry(data[:self.iNodes[inode].size])

    def getImaps(self, inode):
        res = [self.iNodes[inode].fip]
        while True:
            nv = self.iMap[res[-1]]
            if nv >= 0:
                res.append(nv)
                continue
            if nv == -1: # Might need different logic to handle this error
                print("Ran into unallocated imap while attemtping to read inode")
                exit(1)
            break
        return res

    def getFreeImap(self):
        for i in len(self.iMaps):
            if self.iMaps[i] == -1:
                return i

    def write(self, offset, sector):
        file = open(self.filename, "r+b")
        file.seek(offset)
        file.write(sector)
        file.close()

    def writeSector(self, imap, sector):
        self.write(self.meta.dPoolp + imap * self.meta._ssize, sector)

    def writeInode(self, inode):
        location = self.iNodes[inode].offset
        data = self.read(location)
        data[:32] = self.iNodes[inode].toBytes()
        self.write(location, data)

    def writeImap(self, imap):
        location = self.meta.iMapp + imap * 4
        data = self.read(location)
        data[:4] = self.iMaps[imap]
        self.write(location, data)
    
    def writeFile(self, inode, offset, data):
        if offset >  self.iNodes[inode].size:
            print("Tried to write after the end of a file")
            exit(1)
        if offset + len(data) > self.iNodes[inode].size:
            self.iNodes[inode].size = offset + len(data)
            self.writeInode(inode)
        imaps = self.getImaps(inode)
        remainder = offset % self.meta._ssize
        location = imaps[offset // self.meta._ssize]
        sector = self.readSector(location)
        if self.meta._ssize >= len(data) + remainder:
            sector = sector[:remainder] + data + sector[remainder + len(data):]
            self.writeSector(location, sector)
        else:
            amountWritten = self.meta._ssize - remainder
            sector = sector[:remainder] + data[:amountWritten]
            self.writeSector(location, sector)
            while True:
                nlocation = self.iMaps[location]
                if location == -2:
                    nlocation = self.getFreeImap()
                    self.iMaps[location] = nlocation
                    self.writeImap(location)
                sector = self.readSector(location)
                if self.meta._ssize >= len(data) - amountWritten:
                    sector = data[amountWritten:] + sector[len(data) - amountWritten:]
                    self.writeSector(nlocation, sector)
                    return 0
                sector = data[amountWritten:amountWritten + self.meta._ssize]
                self.writeSector(nlocation, sector)
                amountWritten += self.meta._ssize
                location = nlocation


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
    
    def toBytes(self):
        modeBits = (self.mode << 12) & (self.s_ugt << 9) & (self.user << 6) & (self.group << 3) & self.other
        return struct.pack(">2h7i", modeBits, self.linkCount, self.ownerUID, self.ownerGID, self.cTime, self.mTime, self.aTime, self.size, self.fip)


class FileEntry:
    def __init__(self, data):
        self.data = data

    def __repr__(self):
        return self.data.decode()


class DirectoryEntry:
    def __init__(self, data):
        self.inode = bread("i", data[0:4])
        self.name = data[4:].decode()

    def __repr__(self):
        return f"({self.inode}) {self.name}"


if __name__ == "__main__":
    image = Image(sys.argv[1])
    print(image.iMap[:10])
    [print(node) for node in image.iNodes[:10]]
    print(image.readDirectory(0))
    print(image.readFile(2))
    image.writeFile(2, 2, b"lol")
    print(image.readFile(2))
    image.writeFile(2, 2, b"llo")
    print(image.readFile(2))
