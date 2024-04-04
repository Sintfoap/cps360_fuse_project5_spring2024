import sys
import struct
import datetime
import time

def bread(fmt, data):
    """Takes a struct format string and data to read from to return the interpreted data"""
    return struct.unpack(f">{fmt}", data)[0]

class Image:
    """
    Holds the data and in memory portions of file. Also holds 
    all of the functions to interact with the file system.
    """
    def __init__(self, image_file):
        self.image_file = image_file 
        self.meta = MetaData(image_file.read()[:28])
        self.iNodes = self.readIList()
        self.iMap = self.readIMap()
    
    def getImaps(self, inode):
        """
        Return all the imap entries related to an inode.
        """
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
    

    def getNumFreeInodes(self) -> int:
        """
        Calculates and returns the number of free inodes in the system
        """
        count = 0
        for i in self.iNodes:
            if i.mode == 0:
                count += 1

        return count

    def getNumFreeImaps(self) -> int:
        """
        Calculates and returns the number of free blocks in the system
        """
        count = 0
        for i in self.iMap:
            if i == -1 or i == 0:
                count += 1

        return count

    def unallocateImap(self, imap):
        """
        Set an imap to unallocated. We zero out 
        dsectors when we alloc, so not here. 
        """
        self.iMap[imap] = -1
        self.writeImap(imap)

    def truncate(self, inode, nsize):
        """
        Truncate a file to a given size.
        """
        ninode = self.iNodes[inode]
        # do logic for unallocating blocks 
        imaps = self.getImaps(inode)
        for counter, imap in enumerate(imaps[::-1]): # iterate backwards in order to unallocate imaps at end of file first
            if (ninode.size - counter * self.meta._ssize) // self.meta._ssize == nsize // self.meta._ssize:
                self.iMap[imap] = -2 
                self.writeImap(imap)
                break
            self.unallocateImap(imap)
        imap = self.getImaps(inode)[-1]

        # zero out block that the nsize truncate falls in
        nsector = b'\0' * self.meta._ssize 
        nsector = self.readSector(imap)[:nsize % self.meta._ssize] + nsector[nsize % self.meta._ssize:]
        ninode.size = nsize
        self.iNodes[inode] = ninode
        self.writeInode(inode) # write inode first in case of crash
        self.writeSector(imap, nsector)
            
    def read(self, offset):
        """
        Reads size bytes from offset in the file.
        """
        self.image_file.seek(offset)
        return self.image_file.read()[:self.meta._ssize]
    
    def readIList(self):
        """
        Reads in INodes from IList and stores them in memory.
        """
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
        """
        Reads in all IMap entries into memory.
        """
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
        """Return data from a given data sector as indexed by imap."""
        return self.read(self.meta.dPoolp + imap * self.meta._ssize)

    def readDirectory(self, inode):
        """
        A wrapper that uses readFile but parses into DirectoryEntries afterwards.
        """
        file = self.readFile(inode)
        res = []
        for i in range(self.iNodes[inode].size // 32):
            res.append(DirectoryEntry(file.data[i * 32: (i + 1) * 32]))
        return res
            
    def readFile(self, inode):
        """
        Reads by grabbing the start imap out of inode and then
        chaining together until we reach inode.size data.
        """
        imaps = self.getImaps(inode)
        data = b""
        for index in imaps:
            data += self.readSector(index)
        return FileEntry(data[:self.iNodes[inode].size])

    def allocImap(self):
        """
        Finds the first available unallocated imap,
        zeroes it out and returns its index.
        """
        for i in range(len(self.iMap)):
            if self.iMap[i] == -1:
                self.writeSector(i, b"\0" * self.meta._ssize) # zero out block
                return i

    def write(self, offset, sector):
        """
        Writes a sector at the given offset in the file.
        """
        self.image_file.seek(offset)
        self.image_file.write(sector)

    def writeSector(self, imap, sector):
        """
        Calls write on the sector designated by imap.
        """
        self.write(self.meta.dPoolp + imap * self.meta._ssize, sector)

    def writeInode(self, inode):
        """
        Writes an inode back to the file without
        modifying the surrounding inodes.
        """
        location = self.iNodes[inode].offset
        data = self.read(location)
        data = self.iNodes[inode].toBytes() + data[32:]
        self.write(location, data)

    def writeImap(self, imap):
        """
        Writes back the in memory imap to disk.
        """
        location = self.meta.iMapp + imap * 4
        data = self.read(location)
        data = struct.pack(">i", self.iMap[imap]) + data[4:]
        self.write(location, data)
    
    def writeDirectory(self, parent_inode, inode, name):
        """
        Takes in an inode to put an entry into, the parent_inode, an
        inode to link to, and a name and adds an entry to said parent_inode.
        """
        payload = struct.pack(">i28s", inode, name) 
        data = self.readDirectory(parent_inode)
        offset = -1
        for e, dir in enumerate(data):  # find empty dir spot
            if dir.name == "" and dir.data == 0:
                offset = e * 32
                break
        if offset == -1:  # if no open dir entry in all the blocks, then we need to allocate a new block
            offset = len(data) * 32
        self.writeFile(parent_inode, offset, payload)
        self.iNodes[parent_inode].linkCount += 1
        self.writeInode(inode)

    def writeFile(self, inode, offset, data):
        """
        Writes data to the file designated by inode 
        at offset and updates relating metadata. 
        Expands file if necessary.
        """
        if offset >  self.iNodes[inode].size:
            print("Tried to write after the end of a file")
            exit(1)
        if offset + len(data) > self.iNodes[inode].size:  # expand inode size if necessary
            self.iNodes[inode].size = offset + len(data)
            self.writeInode(inode)
        imaps = self.getImaps(inode)
        if offset // self.meta._ssize > (len(imaps) - 1): # allocate imaps if necessary
            nimap = self.allocImap()
            self.iMap[imaps[-1]] = nimap
            self.iMap[nimap] = -2
            self.writeImap(imaps[-2])
            self.writeImap(imaps[-1])
            imaps = self.getImaps(inode)
        remainder = offset % self.meta._ssize
        location = imaps[offset // self.meta._ssize]  # find first sector that we need to write to
        sector = self.readSector(location)
        if self.meta._ssize >= len(data) + remainder:  # first sector write
            sector = sector[:remainder] + data + sector[remainder + len(data):]
            self.writeSector(location, sector)
        else:
            amountWritten = self.meta._ssize - remainder  # write to more sectors as long as there's more data to write
            sector = sector[:remainder] + data[:amountWritten]
            self.writeSector(location, sector)
            while True:
                nlocation = self.iMap[location]
                if location == -2:
                    nlocation = self.allocImap()
                    self.iMap[location] = nlocation
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

    def allocInode(self, inodeType: int, mode: int) -> int:
        """
        Finds the first free inode and allocates it using inodeType.
        If there are no inodes left we print an error and die.
        """
        modeBits = mode
        for e, i in enumerate(self.iNodes):
            if i.mode == 0: # 0 == unallocated
                i.mode = inodeType
                i.s_ugt = (modeBits & 0x0E00) >> 9
                i.user = (modeBits & 0x01C0) >> 6
                i.group = (modeBits & 0x0038) >> 3
                i.other = modeBits & 0x0007
                i.linkCount = 0x01
                i.ownerUID = 0x03E8
                i.ownerGID = 0x03E8
                i.cTime = int(time.mktime((datetime.datetime.now()).timetuple())) # gets the current time and converts it to unix timestamp, convert to int to truncate
                i.mTime = i.cTime
                i.aTime = i.cTime
                i.size = 0
                i.fip = self.allocImap() # assign first free Imap
                self.iMap[i.fip] = -2 # mark as EOF
                self.writeImap(i.fip) # write to file
                return e 

        print("lardinator3000 ERROR: out of inodes")
        exit(-1)

    def linkInode(self, targetInodeNum: int, newInodeNum: int) -> int:
        """
        Copies the necessary data over from an Inode to link new to target
        """
        self.iNodes[newInodeNum].ownerUID = self.iNodes[targetInodeNum].ownerUID
        self.iNodes[newInodeNum].ownerGID = self.iNodes[targetInodeNum].ownerGID
        self.iNodes[newInodeNum].size = self.iNodes[targetInodeNum].size
        self.iNodes[newInodeNum].fip = self.iNodes[targetInodeNum].fip
        self.iNodes[targetInodeNum].linkCount += 1
        return newInodeNum


class MetaData:
    """
    Holds and manages all the metadata in the superblock.
    """
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
    """
    An INode entry. Holds and manages its metadata.
    """
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

    def modeBits(self):
        return (self.mode << 12) | (self.s_ugt << 9) | (self.user << 6) | (self.group << 3) | self.other

    def __repr__(self):
        return " ".join(f"{k} {w}" for k,w in vars(self).items())
    
    def toBytes(self):
        return struct.pack(">2h7i", self.modeBits(), self.linkCount, self.ownerUID, self.ownerGID, self.cTime, self.mTime, self.aTime, self.size, self.fip)


class FileEntry:
    """
    A file entry.
    """
    def __init__(self, data):
        self.data = data

    def __repr__(self):
        return self.data.decode()


class DirectoryEntry:
    """
    A directory entry that points to another inode and holds a name.
    """
    def __init__(self, data):
        self.inode = bread("i", data[0:4])
        self.name = data[4:]
        for i, e in enumerate(self.name):
            if e == 0:
                self.name = self.name[:i].decode()
                break

    def __repr__(self):
        return f"({self.inode}) {self.name}"
