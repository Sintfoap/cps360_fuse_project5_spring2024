# Linked Allocation Resource Directory (LARD) FS

## Abstract

The LARD filesystem (`lardfs`) combines elements of the classic Unix filesystem (i-list/i-nodes, mode-bits, file types, names as links in directory files, unix timestamps and link count) with one from the ubiquitous FAT filesystem (linked-list sector allocation).
LARD is not recommended for production, nor for direct human consumption.
(It provides excellent flavor in scrambled eggs, though.)

## Axioms

The filesystem "root" is always i-node 0.

## On-Disk Format

All numeric fields are **BIG ENDIAN**.
Signed integers are **2's complement**.

* superblock:
    * 8-byte ASCII magic string: "LARDFS\n\0"
    * *(all numeric fields BIG ENDIAN)*
    * 4-byte: sector size (in bytes)
    * 4-byte: start-of-i-list (in sectors)
    * 4-byte: start-of-i-map (in sectors)
    * 4-byte: start-of-d-pool (in sectors)
* i-list: (an array of i-nodes indexed by i-number)
    * 2-byte: mode bits
        * MSB
        * type (0 bits):
            * 0b0011: symlink
            * 0b0010: directory
            * 0b0001: regular file
            * 0b0000: UNUSED/FREE i-node
        * setuid/setgid/sticky (su/sg/t) [3 bits]
        * user [owner] R/W/X [3 bits]
        * group R/W/X [3 bits]
        * other R/W/X [3 bits]
        * LSB
    * 2-byte: link count (0-65535)
    * 4-byte: owner-uid
    * 4-byte: owner-gid
    * 4-byte unix-timestamp: c-time (metadata-change-time)
    * 4-byte unix-timestamp: m-time (data change time)
    * 4-byte unix-timestamp: a-time (data access time)
    * 4-byte: size in bytes
    * 4-byte: first-dsector (index into imap/dpool)
* i-map: (an array of 4-byte dsector indices)
    * one per sector in the dpool
    * serves as a linked-list-style "next sector" pointer, a la FAT
    * an inode's `start` field gives the _first_ sector of a file
    * we then look up that sector's entry in the i-map to see what the _next_ sector in the file is
    * reserved values:
        * -1 (0xffffffff): unallocated
        * -2: EOF (no more sectors in chain)
* d-pool: (an array of sectors available for use)
    * one per index in the imap
* directory file structure: (array of 32-byte dir-entries)
    * 4-byte i-node
    * 28-byte ASCII char name/path-segment (e.g., "etc")
