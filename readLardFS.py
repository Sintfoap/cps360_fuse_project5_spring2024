import sys
import struct

smap = {
        "s": 1,     # char[]
        "i": 4,     # int
        "h" : 2     # short
       }

class LARDIMAGE:
    def __init__(self, filename):
        self._file = open(filename, "rb").read()
        self.fp = 0
        self.magic = self.readfile("8s")
        self.sectorSize = self.readfile("i")
        self.imageSize = self.readfile("i")
        self.iListp = self.readfile("i")
        self.iMapp = self.readfile("i")
        self.dPoolp = self.readfile("i")
        self.iList = self.getiListEntries(self.sectorSize * self.iListp, self._file) # we pass in the sector size * the pointer for the i list
        self.iMap = []
        self.dPool = []

    # returns a list of objs that have metadata about the inodes
    def getiListEntries(self, idx: int, fle) -> list:        
        ct = 0
        lst = []
        while True: # read until we run out of inodes
            entry = iListEntry(idx + ct, fle) # we add ct to index to the next inode each time
            if entry.mode == 0: # when we read and there are no mode bits we have hit the end of the inodes
                break
            lst.append(entry)
            ct += 32 # each inode takes 32 bytes of metadata, so each read we increment the pointer by 32
        return lst
    
    def getiMaps(self, idx: int, fle) -> list:
        return []

    def getdPools(self, idx: int, fle) -> list:
        return []

    def readfile(self,sig):
        size = 0
        for c in sig:
            d = smap.get(c, -1)
            if d == -1:
                size = size * 10 + int(c)
                continue
            size = size * d if size != 0 else d
        newz = self.fp + size
        data = struct.unpack(f">{sig}",  self._file[self.fp: newz])
        self.fp = newz
        return data[0] 
    
    def __str__(self):
        return f"magic: {self.magic}, sectSz: {self.sectorSize}, imgSz: {self.imageSize}, iListp: {self.iListp}, iMapp: {self.iMapp}, dPoolp: {self.dPoolp}"
    

# class for holding data about inode entries
class iListEntry:
    def __init__(self, fp: int, file):
        self._file = file
        self.fp = fp                                # index for where the inodes are in the file
        self.mode = self.getiNodes("h")             # mode bits
        self.linkCount = self.getiNodes("h")        # number of links to this node
        self.ownerUID = self.getiNodes("i")         # owners userid
        self.ownerGID = self.getiNodes("i")         # owners groupid
        self.cTime = self.getiNodes("i")            # time of creation
        self.mTime = self.getiNodes("i")            # time of last modification
        self.aTime = self.getiNodes("i")            # time of last access
        self.nodeSize = self.getiNodes("i")         # size of node
        self.firstDSec = self.getiNodes("i")        # d sector

    # I just stole this from readFile XD
    def getiNodes(self, fmt: str):
        size = 0
        for c in fmt:
            d = smap.get(c, -1)
            if d == -1:
                size = size * 10 + int(c)
                continue
            size = size * d if size != 0 else d
        newz = self.fp + size
        data = struct.unpack(f">{fmt}",  self._file[self.fp: newz])
        self.fp = newz
        return data[0]
    
    # yay __str__
    def __str__(self):
        return (f"mode: {self.mode} linkCt: {self.linkCount}, UID: {self.ownerUID}, GID: {self.ownerGID}, ctime: {self.cTime}, mtime: {self.mTime}, atime: {self.aTime}, size: {self.nodeSize}, dsec: {self.firstDSec}")


class iMapEntry:
    def __init__(self):
        self.nextSector


class dPoolEntry:
    def __init__(self):
        self.sector



image = LARDIMAGE(sys.argv[1])
print(image)
for i in image.iList:
    print(i)
