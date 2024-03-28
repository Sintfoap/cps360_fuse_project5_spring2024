#!/usr/bin/env python3
from __future__ import annotations
import logging
import mmap
import os
import time
import struct
import sys
from typing import BinaryIO


InodeStruct = struct.Struct(">2H7I")

TYPE_REG = 1
TYPE_DIR = 2
TYPE_LNK = 3
MIN_TYPE = TYPE_REG
MAX_TYPE = TYPE_LNK


class File:
    def __init__(self, fs: Filesystem):
        self._inum = len(fs._files)
        fs._files.append(self)
        self._fs = fs
        self._mode = 0x0000
        self._links = 0
        self._uid = os.getuid() # simplify life by making all files owned by the FS creating user/group
        self._gid = os.getgid()
        self._ctime = time.time()
        self._mtime = self._ctime
        self._atime = self._ctime
        self._size = 0
        self._start = 0

    @property
    def inumber(self) -> int:
        return self._inum 

    @property
    def mode(self) -> int:
        return self._mode

    @property
    def links(self) -> int:
        return self._links

    @links.setter
    def links(self, value):
        if value >= 0:
            self._links = value
        else:
            raise ValueError(value)

    @property
    def uid(self) -> int:
        return self._uid

    @property
    def gid(self) -> int:
        return self._gid

    @property
    def ctime(self) -> float:
        return self._ctime

    @property
    def mtime(self) -> float:
        return self._mtime

    @property
    def atime(self) -> float:
        return self._atime

    def chtype(self, type_num: int):
        if MIN_TYPE <= type_num <= MAX_TYPE:
            self._mode = (self._mode & 0o7777) | (type_num << 12)
        else:
            raise ValueError("invalid type")

    def chmod(self, mode_bits: int):
        self._mode = (self._mode & 0xf000) | (mode_bits & 0o7777)

    def chown(self, uid: int, gid: int):
        self._uid = uid
        self._gid = gid

    def touch_ctime(self, when=None):
        if when is None:
            when = time.time()
        self._ctime = when

    def touch_mtime(self, when=None):
        if when is None:
            when = time.time()
        self._mtime = when

    def touch_atime(self, when=None):
        if when is None:
            when = time.time()
        self._atime = when

    @property
    def size(self) -> int:
        return self._size

    @property
    def start(self) -> int:
        return self._start

    def pack_inode_into(self, buffer: memoryview, offset: int):
        InodeStruct.pack_into(buffer, offset, 
            self._mode, self._links, self._uid, self._gid,
            int(self._ctime), int(self._mtime), int(self._atime), 
            self._size, self._start)

    def used_sectors(self) -> int:
        raise NotImplementedError()


class RegularFile(File):
    def __init__(self, fs: Filesystem):
        super().__init__(fs)
        self.chtype(TYPE_REG)
        self.chmod(0o644)
        self._data = bytearray()

    @property
    def data(self) -> bytearray:
        return self._data

    def dump(self, img: Image):
        self._size = len(self._data)
        self._start = img.write_data(self._data)
        img.write_inode(self)

    def used_sectors(self) -> int:
        nbytes = len(self._data)
        ssize = self._fs._sector_size
        return ((nbytes + (ssize - 1)) // ssize)


DirEntryStruct = struct.Struct(">I28s")


class Directory(File):
    def __init__(self, fs: Filesystem):
        super().__init__(fs)
        self.chtype(TYPE_DIR)
        self.chmod(0o755)
        self._data = {b'.': self} # map of names to Files

    def link(self, name: bytes, f: File):
        if len(name) > 28 or b'/' in name:
            raise ValueError(name)
        self._data[name] = f
        f.links += 1

    def unlink(self, name: str):
        del self._data[name]
        f.links -= 1

    def creat(self, name: bytes) -> RegularFile:
        f = RegularFile(self._fs)
        self.link(name, f)
        return f

    def mkdir(self, name: bytes) -> Directory:
        d = Directory(self._fs)
        d.link(b'..', self)
        self.link(name, d)
        return d

    def dump(self, img: Image):
        dir_data = bytearray(len(self._data) * DirEntryStruct.size)
        for i, (name, inode) in enumerate(sorted(self._data.items())):
            DirEntryStruct.pack_into(dir_data, i * DirEntryStruct.size,
                inode.inumber, name)

        self._size = len(dir_data)
        self._start = img.write_data(dir_data)
        img.write_inode(self)

    def used_sectors(self) -> int:
        nbytes = len(self._data) * DirEntryStruct.size
        ssize = self._fs._sector_size
        return (nbytes + (ssize - 1)) // ssize


ImapEntryStruct = struct.Struct(">i")
SuperblockStruct = struct.Struct(">8s5I")

class Image:
    def __init__(self, fs: Filesystem, file: open):
        self._fs = fs
        self._file = file
        
        ss, nsectors, istart, mstart, dstart = fs.geometry()
        self._sector_size = ss
        self._total_sectors = nsectors
        self._ilist_start = istart
        self._ilist_max = mstart - istart
        self._imap_start = mstart
        self._data_start = dstart
        self._data_max = nsectors - dstart

        self._ready = False

    def __enter__(self):
        capacity = self._total_sectors * self._sector_size
        os.truncate(self._file.fileno(), capacity)
        self._mmap = mmap.mmap(self._file.fileno(), capacity)
        self._store = memoryview(self._mmap)
        return self

    def format(self):
        SuperblockStruct.pack_into(self._store, 0, b"LARDFS\n\0", 
            self._sector_size, self._total_sectors,
            self._ilist_start, self._imap_start, self._data_start)
        
        self._b_imap_start = self._imap_start * self._sector_size
        for i in range(self._data_max):
            self._link_map(i, -1)   # mark unused

        self._next_dnode = 0
        self._ready = True

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        self._ready = False
        self._store.release()
        self._mmap.close() 
        return False

    @property
    def sector_size(self) -> int:
        return self._sector_size

    def _link_map(self, from_s: int, to_s: int):
        offset = self._b_imap_start + (from_s * ImapEntryStruct.size)
        ImapEntryStruct.pack_into(self._store, offset, to_s)

    def write_inode(self, file: File):
        if not self._ready:
            raise RuntimeError("not ready")

        if not (0 <= file.inumber < self._ilist_max):
            raise ValueError("inumber out of range")
        
        offset = (self._ilist_start * self._sector_size) + (file.inumber * InodeStruct.size)
        logging.debug(f"writing inode #{file.inumber} ({file._mode=:#o}, {file.links=}) to disk (slice[{offset}:{offset+InodeStruct.size}])")
        file.pack_inode_into(self._store, offset) 

    def write_data(self, data:bytes) -> int:
        '''returns INITIAL sector used'''
        if not self._ready:
            raise RuntimeError("not ready")

        dnodes = []
        for i in range(0, len(data), self._sector_size):
            chunk = data[i:i + self._sector_size]

            dnode = self._next_dnode
            self._next_dnode += 1
            dnodes.append(dnode)

            sstart = (self._data_start + dnode) * self._sector_size
            send = sstart + self._sector_size

            logging.debug(f"writing {len(chunk)} bytes into data sector {dnode} (slice[{sstart}:{send}])")
            self._store[sstart:send] = chunk.ljust(self._sector_size, b'\0')

        for _from, _to in zip(dnodes, dnodes[1:]): 
            logging.debug(f"linking sector {_from} to {_to}") 
            self._link_map(_from, _to)

        logging.debug(f"tagging sector {dnodes[-1]} as EOF")
        self._link_map(dnodes[-1], -2)

        return dnodes[0]
        

class Filesystem:
    def __init__(self, capacity: int, ifactor: float = 0.1, sector_size=512):
        self._capacity = capacity
        self._sector_size = sector_size
        if capacity % sector_size != 0:
            raise ValueError(f"capacity ({capacity}) not divisible by sector_size ({sector_size})")
        self._ifactor = ifactor
        self._files = []
        self._root = Directory(self)
        self._root.link(b'..', self._root)

    @property
    def root(self) -> Directory:
        return self._root

    def size_in_sectors(self, nbytes: int) -> int:
        return (nbytes + (self._sector_size - 1)) // self._sector_size

    def geometry(self) -> tuple[int, int, int, int, int]:
        total_sectors = self.size_in_sectors(self._capacity)

        # calculate sectors dedicated to data (1 - ifactor)
        data_sectors = int(total_sectors * (1.0 - self._ifactor))

        # calculate size of imap (need <data_sectors> entries)
        imap_sectors = self.size_in_sectors(data_sectors * ImapEntryStruct.size)

        # calculate sectors left for inodes ("1" for the superblock)
        inode_sectors = total_sectors - (data_sectors + imap_sectors + 1)

        # region starts for superblock
        inode_start = 1
        imap_start = inode_start + inode_sectors
        data_start = imap_start + imap_sectors

        return (self._sector_size, total_sectors, inode_start, imap_start, data_start)

    def dump(self, fd) -> bytes:
        with Image(self, fd) as img:
            img.format()
            for file in self._files:
                file.dump(img)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        stream=sys.stderr,
    )
    fs = Filesystem(360*1024)
    etc = fs.root.mkdir(b"etc")
    etc_motd = etc.creat(b"motd")
    etc_motd.data.extend("hello, world!\n".encode())

    var = fs.root.mkdir(b"var")
    var_big = var.creat(b"big")
    var_big.data.extend(b"A"*1337)

    with open("lardfs.img", "wb+") as fd:
        fs.dump(fd)

