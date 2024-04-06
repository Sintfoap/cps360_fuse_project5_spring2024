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
        self.image.writeDirectory(parent_inode - 1, inode=ninode, name=name)
        return (ninode + 1, self.getattr(ninode + 1)) # We don't explicity increment lookupCount here because it's set in class INode

    def destroy(self):
        self.image.image_file.close()

    def flush(self, fh):
        log.debug(f"flush {fh}")
        
    def forget(self, inode_list):
        log.debug("forget")
        for inode, nlookup in inode_list:
            if self.image.iNodes[inode - 1].lookupCount > nlookup:
                self.image.iNodes[inode - 1].lookupCount -= nlookup
            elif self.image.iNodes[inode - 1].linkCount == 0: # lookupCount would've been set to zero since lookupCount was <= to nlookup
                self.image.iNodes[inode - 1].mode = 0
            else:
                self.image.iNodes[inode - 1].lookupCount = 0
            self.image.writeInode(inode - 1)

    def fsync(self, fh, datasync):
        log.debug(f"fsync")

    def fsyncdir(self, fh, datasync):
        log.debug("fsyncdir")

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

    def link(self, targetInode, targetInodeDir, new_name, ctx):
        """
        Creates a hard link to an inode
        """
        log.debug("link")
        self.image.writeDirectory(parent_inode=targetInodeDir - 1, inode=targetInode - 1, name=new_name)
        self.image.iNodes[targetInode - 1].linkCount += 1
        self.image.iNodes[targetInode - 1].lookupCount += 1
        return self.getattr(targetInode, ctx)

#   def listxattr(self, inode, ctx):
#       log.debug("listxattr")

    def lookup(self, parent_inode, name, ctx):
        log.debug(f"lookup {name} {parent_inode}")
        directories = self.image.readDirectory(parent_inode - 1)
        for dir in directories:
            if dir.name.encode() == name:
                self.image.iNodes[dir.inode].lookupCount += 1
                self.image.writeInode(dir.inode)
                return self.getattr(dir.inode + 1)
        raise llfuse.FUSEError(errno.ENOENT)
        
   
    def mkdir(self, parent_inode, name, mode, ctx):
        log.debug("mkdir")
        ninode = self.image.allocInode(2, mode)
        self.image.writeDirectory(parent_inode - 1, inode=ninode, name=name)
        return self.getattr(ninode + 1) # We don't explicity increment lookupCount here because it's set in class INode
        
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

    def rename(self, parent_inode_old, name_old, parent_inode_new, name_new, ctx):
        """
        You'll never guess what this function does
        """
        log.debug("rename")
        directories = self.image.readDirectory(parent_inode_old - 1)
        targetInode = None
        for dir in directories:
            if dir.name.encode() == name_old:
                targetInode = dir.inode
                break
        if targetInode == None:
            raise llfuse.FUSEError(errno.ENOENT)
        self.image.writeDirectory(parent_inode_old - 1, name=name_old, delete=True)
        self.image.writeDirectory(parent_inode_new - 1, inode=targetInode, name=name_new)
        return

    def rmdir(self, parent_inode, name, ctx):
        log.debug("rmdir")
        dirs = self.image.readDirectory(parent_inode - 1)
        inode = -1
        for dir in dirs:
            if dir.name.encode() == name:
                inode = dir.inode
        if inode == -1:
            raise llfuse.FUSEError(errno.NOENT)
        dirs = self.image.readDirectory(inode)
        if len(dirs) != 0:
            raise llfuse.FUSEError(errno.ENOTEMPTY)
        self.image.writeDirectory(parent_inode - 1, name=name, delete=True)
        self.image.wipe(inode)
                
    def setattr(self, inode, attr, fields, fh, ctx):
        log.debug("setattr")
        if fields.update_size:
            self.image.truncate(inode - 1, attr.st_size)
        if fields.update_mode:
            self.image.iNodes[inode - 1].chmod(attr.st_mode)
        if fields.update_uid:
            self.image.iNodes[inode - 1].ownerUID = attr.st_uid
        if fields.update_gid:
            self.image.iNodes[inode - 1].ownerGID = attr.gid
        if fields.update_atime:
            self.image.iNodes[inode - 1].aTime = attr.st_atime_ns
        if fields.update_mtime:
            self.image.iNodes[inode - 1].mTime = attr.st_mtime_ns
        self.image.writeInode(inode - 1)
        return self.getattr(inode)


       
#   def setxattr(self, inode, name, value, ctx):
#       log.debug("setxattr")

#   def stacktrace(self):
#       log.debug("stacktrace")
#       raise llfuse.FUSEError(errno.ENOSYS)

    def statfs(self, ctx):
        """
        returns statistics about the file system in the statvfs struct from llfuse.StatvfsData()
        test using df --block-size 512
        """
        log.debug("statfs")
        stat_ = llfuse.StatvfsData()

        stat_.f_bsize = 512
        stat_.f_frsize = 768
        
        size = 512 * stat_.f_frsize
        stat_.f_blocks = size // stat_.f_frsize
        sz = self.image.getNumFreeImaps() * 512
        stat_.f_bfree = sz // stat_.f_frsize # I dont know why the math maths this way, but it doesnt work any other way 
        stat_.f_bavail = stat_.f_bfree 

        stat_.f_files = len(self.image.iNodes)
        stat_.f_ffree = self.image.getNumFreeInodes()
        stat_.f_favail = stat_.f_ffree

        stat_.f_namemax = 28

        return stat_
      

    def symlink(self, parent_inode, linkName, targetName, ctx):
        """
        Receives a directory inode, the name of the link, and the target file name in bytes
        Words cannot describe my confusion and outrage when I figured out that the name of the target was passed in instead of the inode
        Also, doing ln -s will give an input/output error, but I don't know why
        """
        log.debug("symlink")
        directories = self.image.readDirectory(parent_inode - 1)
        targetInode = None
        for dir in directories:
            if dir.name.encode() == targetName:
                targetInode = dir.inode
                break
        if targetInode == None:
            raise llfuse.FUSEError(errno.ENOENT)
        ninode = self.image.allocInode(3, self.image.iNodes[targetInode].modeBits()) # allocate a new inode specifying or-ing the bits to make it a symlink
        self.image.softLinkInode(targetInode, ninode, len(linkName)) # copy the necessary fields
        self.image.writeDirectory(parent_inode - 1, inodl=ninode, name=linkName) # write to dir
        return self.getattr(ninode + 1) # ret

    def unlink(self, parent_inode, name, ctx):
        log.debug("unlink")
        directories = self.image.readDirectory(parent_inode - 1)
        targetInode = None
        for dir in directories:
            if dir.name.encode() == name:
                targetInode = dir.inode
                break
        if targetInode == None:
            raise llfuse.FUSEError(errno.ENOENT)
        self.image.writeDirectory(parent_inode - 1, name=name, delete=True)
        self.image.iNodes[targetInode].linkCount -= 1
        if self.image.iNodes[targetInode].linkCount == 0 and self.image.iNodes[targetInode].lookupCount == 0:
            self.image.iNodes[targetInode].mode = 0 
        self.image.writeInode(targetInode)

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

