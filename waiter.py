#!/usr/bin/python3
from __future__ import annotations
import argparse
import logging
import sys
import os
import stat
from typing import BinaryIO
import errno

import llfuse
from lardinator3000 import *

import faulthandler
faulthandler.enable()

log = logging.getLogger(__name__)

class LardFS(llfuse.Operations):
    def __init__(self, image_file: BinaryIO):
        super().__init__()
        self.image = Image(image_file)
    
#   def access(self, inode, mode, ctx):
#       log.debug("access")
#       raise llfuse.FUSEError(errno.ENOSYS)

    def create(self, parent_inode, name, mode, flags, ctx):
        log.debug("create")
        ninode = self.image.allocInode(1, mode)
        self.image.writeDirectory(parent_inode - 1, ninode, name)
        return (ninode + 1, self.getattr(ninode + 1))
        

    def destroy(self):
        self.image.image_file.close()

    def flush(self, fh):
        log.debug(f"flush {fh}")
        
#   def forget(self, inode_list):
#       log.debug("forget")
#       raise llfuse.FUSEError(errno.ENOSYS)

    def fsync(self, fh, datasync):
        log.debug(f"fsync {fh}")

#   def fsyncdir(self, fh, datasync):
#       log.debug("fsyncdir")
#       raise llfuse.FUSEError(errno.ENOSYS)

    def getattr(self, inode, ctx=None):
        inodeEntry = self.image.iNodes[inode - 1]
        entry = llfuse.EntryAttributes()
        entry.st_ino = inode
        entry.st_mode = (stat.S_IFDIR if inodeEntry.mode == 2 else stat.S_IFREG if inodeEntry.mode == 1 else stat.S_IFLNK) | (inodeEntry.modeBits() & 0x0FFF)
        entry.st_nlink = inodeEntry.linkCount
        entry.st_gid = inodeEntry.ownerGID
        entry.st_uid = inodeEntry.ownerUID
        entry.st_rdev = 0
        entry.st_size = inodeEntry.size
        entry.st_blksize = self.image.meta._ssize
        entry.st_blocks = inodeEntry.size // self.image.meta._ssize
        entry.generation = 0
        entry.attr_timeout = 1
        entry.entry_timeout = 1
        entry.st_atime_ns = inodeEntry.aTime
        entry.st_ctime_ns = inodeEntry.cTime 
        entry.st_mtime_ns = inodeEntry.mTime
        return entry


#   def getxattr(self, inode, name, ctx):
#       log.debug("getxattr")
#       raise llfuse.FUSEError(errno.ENOSYS)

#   def link(self, inode, new_parent_inode, new_name, ctx):
#       log.debug("link")
#       raise llfuse.FUSEError(errno.ENOSYS)
#       
#   def listxattr(self, inode, ctx):
#       log.debug("listxattr")
#       raise llfuse.FUSEError(errno.ENOSYS)

    def lookup(self, parent_inode, name, ctx):
        log.debug(f"lookup {name} {parent_inode}")
        directories = self.image.readDirectory(parent_inode - 1)
        for dir in directories:
            if dir.name.encode() == name:
                return self.getattr(dir.inode + 1)
        raise llfuse.FUSEError(errno.ENOENT)
        
   
    def mkdir(self, parent_inode, name, mode, ctx):
        log.debug("mkdir")
        ninode = self.image.allocInode(2, mode)
        self.image.writeDirectory(parent_inode - 1, ninode, name)
        return self.getattr(ninode + 1)
        

#   def mknod(self, parent_inode, name, mode, rdev, ctx):
#       log.debug("mknod")
#       raise llfuse.FUSEError(errno.ENOSYS)

    def open(self, inode, flags, ctx):
        log.debug(f"open {inode}")
        return inode

    def opendir(self, inode, ctx):
        return inode

    def read(self, fh, off, size):
        log.debug("read")
        return self.image.readFile(fh - 1).data[:size]

    def readdir(self, fh, off):
        entries = []
        for dir in self.image.readDirectory(fh - 1):
            attr = self.getattr(dir.inode + 1)
            entries.append((attr.st_ino, dir.name.encode(), attr))

        for (ino, name, attr) in entries:
            if ino <= off:
                continue
            yield(name, attr, ino)

#   def readlink(self, inode, ctx):
#       log.debug("readlink")
#       raise llfuse.FUSEError(errno.ENOSYS)

    def release(self, fh):
        log.debug(f"release {fh}")

    def releasedir(self, fh):
        log.debug(f"releasedir {fh}")

#   def removexattr(self, inode, name, ctx):
#       log.debug("removexattr")
#       raise llfuse.FUSEError(errno.ENOSYS)

#   def rename(self, parent_inode_old, name_old, parent_inode_new, name_new, ctx):
#       log.debug("rename")
#       raise llfuse.FUSEError(errno.ENOSYS)

#   def rmdir(self, parent_inode, name, ctx):
#       log.debug("rmdir")
#       raise llfuse.FUSEError(errno.ENOSYS)

#   def setattr(self, inode, attr, fields, fh, ctx):
#       log.debug("setattr")
#       raise llfuse.FUSEError(errno.ENOSYS)
#       
#   def setxattr(self, inode, name, value, ctx):
#       log.debug("setxattr")
#       raise llfuse.FUSEError(errno.ENOSYS)

#   def stacktrace(self):
#       log.debug("stacktrace")
#       raise llfuse.FUSEError(errno.ENOSYS)

#   def statfs(self):
#       log.debug("statfs")
#       raise llfuse.FUSEError(errno.ENOSYS)
#       
#   def symlink(self, parent_inode, name, target, ctx):
#       log.debug("symlink")
#       raise llfuse.FUSEError(errno.ENOSYS)

#   def unlink(self, parent_inode, name, ctx):
#       log.debug("unlink")
#       raise llfuse.FUSEError(errno.ENOSYS)

    def write(self, fh, off, buff):
        log.debug(f"write {fh}")
        self.image.writeFile(fh - 1, off, buff)
        return len(buff)
        

def init_logging(debug=False):
    formatter = logging.Formatter('%(asctime)s.%(msecs)03d %(threadName)s: '
                                  '[%(name)s] %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    if debug:
        handler.setLevel(logging.DEBUG)
        root_logger.setLevel(logging.DEBUG)
    else:
        handler.setLevel(logging.INFO)
        root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


def parse_args(argv: list[str]):
    parser = argparse.ArgumentParser()
    parser.add_argument("image_file", type=argparse.FileType(mode='rb+'),
			help="LARD-formatted disk image file")
    parser.add_argument('mountpoint', type=str,
                        help='Where to mount the file system')
    parser.add_argument('--debug', action='store_true', default=False,
                        help='Enable debugging output')
    parser.add_argument('--debug-fuse', action='store_true', default=False,
                        help='Enable FUSE debugging output')
    return parser.parse_args(argv[1:])


def main(argv: list[str]):
    options = parse_args(argv)
    init_logging(options.debug)
    lardfs = LardFS(options.image_file)

    log.debug("Mounting...")

    llfuse.init(lardfs, options.mountpoint, ['fsname=lardfs'])
    try:
        llfuse.main()
    except:
        llfuse.close()
        raise

    log.debug("Unmounting...")
    llfuse.close()


if __name__ == '__main__':
    main(sys.argv)

