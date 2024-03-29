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
        self.getiMaps()
        self.getdPools()

    def getiListEntries(self, idx: int, fle) -> list:        
        """Reads a list of objs that contain the metadata of the inodes"""
        ct = 0
        lst = []
        while True: # read until we run out of inodes
            entry = iListEntry(idx + ct, fle, len(lst)) # we add ct to index to the next inode each time
            if entry.mode == 0: # when we read and there are no mode bits we have hit the end of the inodes
                break
            lst.append(entry)
            ct += 32 # each inode takes 32 bytes of metadata, so each read we increment the pointer by 32
        return lst
    
    def getiMaps(self) -> list:
        """
        So the principle for this is we've got an array of 4 byte entries
        that denotate where we have sectors in the dpool. For instance, 
        say for inode 0 the dstart is 2 (yes I'm refering to 2 being the root dir inode),
        if we look at iMapp * sectorSize  + 4 * dstart that gives us 
        the imap entry which is one of three things:
            -1 (0xffffffff) -> unallocated
            -2 (0xfffffffe) -> EOF (no more sectors in file)
             x -> 4 byte entry pointing to next imap entry
        We keep following that chain to find all the sectors in the chain
        till we equal or exceed the inode size.
        """
        for iNode in self.iList:
            size = iNode.nodeSize
            iNode.dsecPointers = [iNode.firstDSec]
            while True:
                self.fp = self.iMapp *  self.sectorSize + 4 * iNode.dsecPointers[-1]
                size -= 512
                entry = self.readfile("i")
                if entry == -2:
                    if size > 0:
                        print("iNode doesn't have enough sectors allocated for its self-claimed voracity.")
                        exit(1)
                    break
                if entry == -1:
                    print("In following sector chain in imap we ran into an unallocated sector. Image is cursed or something, please rebuild or troubleshoot.")
                    exit(1)
                iNode.dsecPointers.append(entry)
            
    def getdPools(self) -> list:
        """
        Ok, this is where we actually read in the file tree. Fun stuff!
        Currently we have implemented two types of files, directories and files
        directories contain 2 bits of info:
            inode: which inode they refer to 
            name: what to display as 
        files just contain data in the files
        so for instance we could have a structure that looks like:
        inode_0[
                dEntry(0, "."),
                dEntry(0, ".."),
                dEntry(1, "etc"),
                dEntry(2, "var"),
                ]
        inode_1[
                dEntry(1, "."),
                dEntry(0, ".."),
                dEntry(3, "motd")
                ]
        inode_2[
                dEntry(2, "."),
                dEntry(0, "..")
                ]
        inode_3[
                fEntry("Hello World!")
                ]
        and the file structure would look like this:
            .
            ..
            etc/
                .
                ..
                motd - Contains data "Hello World!"
            var/
                .
                ..
        """
        for iNode in self.iList:
            size = iNode.nodeSize
            counter = 0
            total_read = 0
            if iNode.mode == 1: # file logic
                data = b""
                while size - total_read > 0:
                    self.fp = self.sectorSize * (self.dPoolp + iNode.dsecPointers[counter])
                    data += self.readfile("512s")
                    total_read += 512
                    counter += 1
                iNode.entries.append(fEntry(data))
            elif iNode.mode == 2: # directory logic
                while size - total_read > 0:
                    for i in range(16):
                        self.fp = (i * 32) + self.sectorSize * (self.dPoolp + iNode.dsecPointers[counter])
                        inode = self.readfile("i")
                        name = self.readfile("28s")
                        iNode.entries.append(dEntry(inode, name))
                        total_read += 32
                        if size - total_read <= 0:
                            break
                    counter += 1

            else:
                print("Logic hasn't been implemented for anything other than directories and files.")
                exit(1)

    def readfile(self,fmt):
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
    
    def __str__(self):
        return f"magic: {self.magic}, sectSz: {self.sectorSize}, imgSz: {self.imageSize}, iListp: {self.iListp}, iMapp: {self.iMapp}, dPoolp: {self.dPoolp}"

    def printTree(self):
        if len(self.iList) == 0:
            print("tree was empty")
        else:
            self.printNode(self.iList[0], 0)
    
    def printNode(self, node, indent):
        prefix = "  "*indent
        if node.mode == 2:
            for entry in node.entries:
                print(prefix + entry.name)
                if entry.inode > node.inumber:
                    self.printNode(self.iList[entry.inode], indent + 1)
        return
    
# class for holding data about inode entries
class iListEntry:
    def __init__(self, fp: int, file, inumber):
        self._file = file
        self.fp = fp                                # index for where the inodes are in the file
        self.inumber = inumber                      # inode's number
        modeBits = self.getiNodes("h")              # mode bits
        self.mode = (modeBits & 0xf000) >> 12       # mode
        self.s_ugt = (modeBits & 0x0E00) >> 9       # setuid/setgid/sticky
        self.user = (modeBits & 0x01C0) >> 6        # user [owner] R/W/X
        self.group = (modeBits & 0x0038) >> 3       # group R/W/X
        self.other = modeBits & 0x0007              # other R/W/X
        self.linkCount = self.getiNodes("h")        # number of links to this node
        self.ownerUID = self.getiNodes("i")         # owners userid
        self.ownerGID = self.getiNodes("i")         # owners groupid
        self.cTime = self.getiNodes("i")            # time of creation
        self.mTime = self.getiNodes("i")            # time of last modification
        self.aTime = self.getiNodes("i")            # time of last access
        self.nodeSize = self.getiNodes("i")         # size of node
        self.firstDSec = self.getiNodes("i")        # d sector
        self.dsecPointers = []                      # pointers to allocated dsectors
        self.entries = []                           # files in this inode

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
        return (f"mode: {self.mode} s_ugt: {self.s_ugt} user: {self.user} group: {self.group} other: {self.other} linkCt: {self.linkCount}, UID: {self.ownerUID}, GID: {self.ownerGID}, ctime: {self.cTime}, mtime: {self.mTime}, atime: {self.aTime}, size: {self.nodeSize}, dsec: {self.firstDSec}")

class dEntry:
    def __init__(self, inode, name):
        self.inode = inode
        self.name = name.decode()

    def __repr__(self):
        return self.name

class fEntry:
    def __init__(self, data):
        self.data = data.decode()

    def __repr__(self):
        return self.data

if __name__ == "__main__":
    image = LARDIMAGE(sys.argv[1])
    print(image)
    for i in image.iList:
        print(i)
    image.printTree()
