import sys
import struct

smap = {
        "s": 1,
        "i": 4,
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
        self.iList = []
        self.iMap = []
        self.dPool = []


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
        return data

image = LARDIMAGE(sys.argv[1])
print(image.sectorSize, image.imageSize, image.iListp, image.iMapp, image.dPoolp)
