# Project 5 - FUSE

***Cps 360 | Spring 2024***

**Contributers:** *Edward Taylor, Ryan Moffitt*

[TOC]

## Setup

### Platform

We’ve tried this on WSL to see if we could get it to work without a VM for Windows users, but that was very broken. We also tried using a Debian 11 VM using VMWare, but that also didn’t work. In all fairness, that might have been a corrupted VM image. At the end of the day, we both ended up using Linux Mint 21.

### Required Software

- Linux, FreeBSD, NetBSD or MacOS X system – We only did Linux, so can’t vouch for the process on any of the others.
- Python – We were using 3.10.12 at the time of writing.
- setuptools – Python module
- contextlib2 – Python module
- pkg-config
- attr
- C compiler
- llfuse

### Build

Make sure to run the update upgrade tools to get the newest versions of software:

```sh
sudo apt update
sudo apt upgrade
```

To install Python on Linux Mint run the following:

```sh
sudo apt install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install python3.10
```

Upon installing python, we can move on to grabbing the rest of the libraries for the project. Next we need python’s package manager, pip, as well as a few linux packages:

```sh
sudo apt install pip
sudo apt install pkg-config
sudo apt install attr
```

After that, we can install some python packages for running llfuse, as well as the dev headers:

```sh
pip install setuptools
pip install contextlib2
sudo apt install libfuse-dev
```

And then, finally, we can run the magic command:

```sh
pip install llfuse
```

### Repo Business

Navigate to the directory in which you want to store the repository and run the following:

```sh
git clone https://github.com/Sintfoap/cps360_fuse_project5_spring2024.git
```

Now would probably be a good time to remind you to have git installed on your linux machine.
Simply run python3 mklardfs.py to create a lardfs.img and you’re good to go!

## LARD

### Description

The LARD filesystem (lardfs) combines elements of the classic Unix filesystem (i-list/i-nodes, mode-bits, file types, names as links in directory files, unix timestamps and link count) with one from the ubiquitous FAT filesystem (linked-list sector allocation). LARD is not recommended for production, nor for direct human consumption. (It provides excellent flavor in scrambled eggs, though.)

### Axioms

- The filesystem “root” is always i-node 0.
- All numeric fields are in big endian.
- Signed integers are 2’s complement.

### Format

- superblock:
  - 8-byte ASCII magic string: "LARDFS\n\0"
  - (all numeric fields BIG ENDIAN)
  - 4-byte: sector size (in bytes)
  - 4-byte: image size (in sectors)
  - 4-byte: start-of-i-list (in sectors)
  - 4-byte: start-of-i-map (in sectors)
  - 4-byte: start-of-d-pool (in sectors)
- i-list: (an array of i-nodes indexed by i-number)
  - 2-byte: mode bits [0xttttsssuuugggooo]
    - MSB
    - type (4 bits):
    - 0b0011: symlink
    - 0b0010: directory
    - 0b0001: regular file
    - 0b0000: UNUSED/FREE i-node
    - setuid/setgid/sticky (su/sg/t) [3 bits]
    - user [owner] R/W/X [3 bits]
    - group R/W/X [3 bits]
    - other R/W/X [3 bits]
    - LSB
  - 2-byte: link count (0-65535)
  - 4-byte: owner-uid
  - 4-byte: owner-gid
  - 4-byte unix-timestamp: c-time (metadata-change-time)
  - 4-byte unix-timestamp: m-time (data change time)
  - 4-byte unix-timestamp: a-time (data access time)
  - 4-byte: size in bytes
  - 4-byte: first-dsector (index into imap/dpool)
- i-map: (an array of 4-byte dsector indices)
  - one per sector in the dpool
  - serves as a linked-list-style "next sector" pointer, a la FAT
  - an inode's start field gives the first sector of a file
  - we then look up that sector's entry in the i-map to see what the next sector in the file is
  - reserved values:
    - -1 (0xffffffff): unallocated
    - -2: EOF (no more sectors in chain)
- d-pool: (an array of sectors available for use)
  - one per index in the imap
- directory file structure: (array of 32-byte dir-entries)
  - 4-byte i-node
  - 28-byte ASCII char name/path-segment (e.g., "etc")

### Format Explination

#### The superblock

Just like images or elf files or what have you, this has a magic string to tell the computer what kind of file it is. We then unpack the sector size which we’re going to immediately turn around and use in relation to the next 4 fields. In understanding these fields, we only need look at the last three, image size is self-explanatory. We can treat the other three as pointers, in essence, to the start of arrays containing the data they’re named after. I’ll discuss what’s exactly in those and what they mean in relation to each other in the following sections.

#### The I-List

This is what you’re going to be doing the most work in. The I-List is a list of i-nodes and their metadata. To start off, we’ve got a nice confusing 2-byte field that contains 5 pieces of information, Yay! I find it useful to look at what this would be represented as in byte format:
`0bttttsssuuugggooo`
The 0b just notates that this is in binary format, so no need to worry about those characters. The next four t’s represent the file type bits, and as noted above there are four different file types we’re worried about right now. The next three bits are the setuid/setgid/sticky bits, then we have the user bits, the group bits, and finally the other bits. This makes up the permissions section of files. We then have the link count, which notates how many references there are to this i-node, such as its own . reference or the .. reference in its child directory. We then have the owner uid and gid, which we don’t have to worry about very much to start with. Then all the timestamps, which will be important for information display. And then the size of bytes, which is very important for parsing, and the first-dsector. This part was super confusing when I was first working on it, this is the first index into both the i-map array and the dpool array. A bit on that next.

#### The I-Map

Ok so the I-Map is basically a linked list of pointers to sectors in the dpool that we’ve allocated for our file. It’s by file, so each I-node has its own start into the I-map/dpool structures. For instance, we might have an i-node that has a first-dsector of 0, and another that has a first-dsector of 4. The ubiquitous equation for getting the relevant pointer is `filePointer = startImap * sectorSize + 4 * dsectorPointer` (dsectorPointer can be first-dsector or any resulting dsectors as you will see in a minute). After we’ve found the first dsector via first-dsector, that will be one of three values. The first is -1 (0xfffffff), which signifies an unallocated sector. We shouldn’t, and I mean error if you do, hit one of these when traversing an existing file image. The second value is -2 (0xfffffffe), which signifies EOF. When you hit this you can stop traversing the file image for the inode you were on. The final value you can get is any positive value. When you get that, that becomes your new dsectorPointer, meaning you can follow that offset into the I-Map array and dpool array to get the next sector. So given the example of the i-node that starts with a dsector of 0, we’d go to `sectorSize * startIMap + 4 * (0)` and look at the value there. Supposing it’s 1, we would then look at `secotrSize * startIMap + 4 * (1)` to get the next dsector. We keep doing that until we hit -2.

#### The D-Pool

The d-pool holds two kinds of information. Files or directories, as denotated by the inode you’re searching for data for. For directory file types, you’re going to go to the first dsector section you found from the I-Map, and then you’re going to get the 4 bytes for the inode and the 28 bytes for the name. This was a bit confusing to begin with so I’ll do my best to explain. The inode designates which iNode holds the data that goes under the corresponding name. So if I’m reading inode 0 and I find an entry that has an inode number of 0 and a name of “.”, then the “.” Refers to inode 0, which is me. If I find an inode number 1 that corresponds to the name “etc”, I’ll have to go look for the data under etc to see what it is. The other type of data is file data, which is just the data that goes in the file. So if inode 0 finds a d-pool entry that points at inode 2 called motd, and inode 2 is a file type inode, then the data we pull up will be the text inside of motd. Now I hear you asking, “how do we know how much data to read from the d-pool for each inode?” and that’s an excellent question. That’s where the size on each inode we pulled in the i-list step comes in handy. For each directory inode, the size attribute will be divisible by 32, and that corresponds to the number of directory entries we should read in. For file types, it can be any arbitrary length, meaning that we just read that many bytes into the file. Now the tricky bit is when your size for an inode is larger than the sectorSize of your file image. In that case your info is going to be split up across sectors and that’s where the linked list nature of the imap comes in handy. Just traverse the imap to the next sector location and continue reading in data at that location in the dpool.

## readLardfs.py

To start out, we first made a python program capable of reading in and outputting the file tree of a LARD file system. Something to be noted here is we used the struct library for python a ton to read in binary fields from the lardfs image. It just made processing a lot easier and faster. The next few sections will be dedicated to how exactly we went about that.

### LARDIMAGE

The class lardimage contains the entirety of the file system image, and handles all the interactions between the inodes and the data in the file. This starts by reading in the superblock, which is pretty simple compared to some of the stuff we do later. We then get the iListEntries, where we read iListEntry objects into the iList attribute until we hit an entry that has a null bit in place of its mode. After that we read in the imap and store all the resulting sector locations in the iListEntry objects, and the same with dpool and entries.

### getImaps

The process by which we retrieve I-Maps is a bit fun, so I’ll take some time to cover it. The basic premise is we want to read through the iList and grab all of the sector locations to store locally in each iListEntry object. In order to do so we record the size of the inode that we’re currently on in our iteration and check it against how much we’ve read in. We do this because we want to make sure that we’ve read enough entries to cover the data we will attempt to read in later. We then calculate where we’re reading from and read 4 bytes in to look for the next entry. If it’s negative 2, Great! Just check to make sure we have enough sectors to cover our size and we’re done! If it’s negative 1, someone done messed up! Report error and move on. If neither of those cases happened, then we have the next location in our list and we continue through our while loop.

### getdPools

So this one’s a bit more complex than getIMaps just because it has another option that’s pendant on a different size. Basic premise is that we want to read in all the data for either directories or files from a given inode. If it’s directories, then we’re always reading a 32 byte chunk till we reach the end of our size. If it’s files then we’re reading data in sectorSize chunks till we reach the end of our size. Pointer math is a bit more fun, and size management is more complex but other than that it’s pretty straightforward.

### IListEntry

Holds all the metadata for i-lists. The two fields to really watch out for are dsecPointers and entries. dsecPointers holds all the pointers to our available, allocated sectors in the dpool which we populate during getIMap. The entries are the fEntrys or dEntrys that we generate during the getdPool process. We do some fun bitwise calculations for separating the 3 bit and 4 bit fields in mode and user permissions from the modeBits, but other than that there’s not much to it.

## lardinator3000.py

Some troubles came up due to our last implementation of parsing lardfs images, mainly the fact that we weren't set up in any reasonable way to write back to the image. `readLardFS.py` did a fantastic job of parsing out the directories, but that's just it. That's all it did. In order to be able to implement the API calls for FUSE, we needed to have a much better way of maintaining the file structure during reads and modifications while still being fairly easy to expand. For our case, we prioritized simplicity over efficiency, meaning that some of the code written here is very dumb, but that's on purpose. Due to that being our goal, we kept the filesystem modifications purely synchronous which, while being unrealistic, made it much easier to maintain and expand. I'll explain in this section how our code works logically, and in the next section I'll explain how that meshes with llfuse.

### Image

This class holds the references to all the other in memory data and handles all reads and writes. We subdivided the data between the `Metaclass`, which handles the superblock, and the `INode` class. `IMaps` didn't get their own class since those can be easily maintained as a list of integers. The class only takes one parameter beyond its instance variable, that parameter being `image_file`. This is an open binary file that handles both reading and writing back to disk. When reading in `MetaData` you'll notice that I don't use the instance method `read`, that's because `read` uses one of the variables in the superblock, so I have to read this in seperately. I'll discuss some of the instance methods in this class after discussing some of the auxilliary classes.

### MetaData

This class handles all of the meta data related to the overall file image. We decided to read in all the pointers in as byte relative offsets instead of sector relative offsets due to the fact that we were going to convert them whenever we used them anyway. I originally made `_ssize` a private variable since I didn't think about having to use it anywhere else, but by the time I realized it was used pretty much everywhere I didn't feel like changing it because of the lore.

### INode

`INode` is a bit more fun than `MetaData` mainly because it just has data that gets modified more often. First off we have the fun business of splitting apart the `modeBits` into their seperate attributes. Something to note is that we record the `offset` of the `INode` in the `INode`'s instance variables, and the reason for that is just for ease of writeback. I also wrote a method for converting the `modeBits` back into their original compressed form partially just for writeback, but also because we need those as a unit for llfuse functionality. Due to the relative complexity of this data structure I also wrote a `toBytes` function just so that we didn't have to do that in the disk writeback function.

### FileEntry and DirectoryEntry

These two are very close in structure and also interact with eachother a lot, so I grouped them together. `FileEntry` is what we shove all the data that we read in from disk into, and if it's a normal file, that's where the reads lifecycle ends, but if it's a directory, then we take the data from `FileEntry` and in essence wrap it in `DirectoryEntry`. The fun business with parsing the name field in `DirectoryEntry` is due to the fact that we do searches on names in llfuse and I was having problems with the name that llfuse passed me and this name being different by null bytes, so sanitization.

### readIList

Now we get into the real meat of `lardinator3000.py`. This is still part of the reading in of the disk, but it starts revealing how all of our data is going to interact with itself. Most of this code is pretty easy to understand, so I won't give a line by line explination, but I will note some interesting implementation details. For instance, as opposed to `readLardFS.py`, we don't just read in the active Inodes, but all of them and as noted in `INodes` we recored the offset into the file and then parse the inode entry.

### readIMap

Pretty much logically equivilant to `readIList` but for imaps. We're also reading in all the IMaps, but there's no custom data structure for this, it's just a generic list of integers. This is because it's super easy to modify a list of ints and write it back, as well as using entries as indexes into the same list, which is what we want to do for imaps.

### read

Now we've finished the inital reading in process, and the rest of the code will be methods we call for interacting dynamically with the `Image` itself. I'm going to approach this from the bottom up, building on functions until we see what the end resulting usecase is. The `read` call is what every function, barring `MetaData` initialization, interfaces with to get data from disk. You'll also notice that this function only reads in sector sized blocks, which is about as realistic as we got with the system. Also probably not being as efficiant as I could be by reading in all of the data from offset on and then trimming it, but as stated before, efficiency wasn't the goal.

### readSector

This is just a translation function from imap indexes to offsets into the file because I found myself using this logic a ton.

### readFile

`readFile` takes in an inode and reads all its data. Now something to note that this can be used to read both regular files or directories, and I'll get more into that in the next subsection. It first walks the `Imap` list to find all the imaps related to the `INode`, and then does a read sector on each of them. When recieving all the info we then trim it down to the size as dennotated by the `INode` just so that we can be guarenteed to deal with that size of data in other functions.

### readDirectory

`readDirectory` is a, in my opinion, clever abstraction of `readFile`. This uses readFile to get the information related to the inode passed in and then just parses that into `DirectoryEntries`.

### write

Similar to `read`, everything goes through this function to write back to disk and it only writes in sector segments. This means we have to be careful not to overwrite surrounding data in the sector we're writing back to, but that's the responsibility of the functions forming the data.

### writeSector

Also similar to `readSectors` this is just an alias for the process of mapping imaps to file offsets and then writing at that position.

### writeFile

Perhaps the most complex function in this program, `writeFile` does exactly what it claims to do, it writes to a file. The main complexity of this function is due to the fact that it has to be able to expand the inode dynamically, and it has to be able to overwrite just the required data without zeroing out any remaining data. What this ends up looking like is we check to see if the size is going to be bigger than the previous size of the inode, which would mean we need to expand the file size. If so we start by modifying the `INode` metadata and then if it's big enough that we need to allocate additional imaps, we do just that using the `allocImap` and `writeImap` functions. After we've done all the prep work we can start going through all the imap sectors and modifying the data we need to. One thing to note is that we made an executive decision to not allow the user to write starting past the end of the file. The first sector write that we do is unique do to the fact that we might have to offset ourselves into it. Every sector write after that is merely checking to see if we still have data to write into the next sector, and if not only write the data that we have left not touching any of the remaining data.

### writeImap and writeInode

These two functions are utility functions to write metadata back to the disk. In `writeFile` we use `writeImap` to write back our newly allocated sectors, and we use `writeInode` to update the size and potentially eventually the modification time of the `INode`.

### allocImap

This is a fairly simple function that finds the first unallocated `Imap` and returns its address. It also zeros out the data in the related sector in case there was any garbage left in their. Perhaps a security risk to have data left after being unallocated, but it was easiest this way.

### truncate and unallocateImap

These two are related because truncate is the only thing other than file deletion that causes Imap freeing. Truncate takes a file and shrinks it down to the designated size. One of the really annoying problems I had with this was trying to calculate whether we needed to free an imap. Turns out it was pretty simple by just doing integer division and seeing if the current index falls in the new index sector, but it's much more complex when you mistake modulo for integer divide.

### allocInode

The start of file creation! This function is pretty self explanitory, it creates an `INode` of `inodeType` file type. This also handles the initial setting of permission bits, so that can get a bit exciting.

## SousTest.py

This is the unit test file that POC's all of our functionallity. Annoying to write, but actually pretty fantastic to be able to run this to check to make sure that it's not the controller that's broken and it's actually whatever I did in llfuse implementation.

### testRead

Very simple test to prove that we can read a file.

### testWrite

This test demonstrates taht we can write inside of a file withotu expanding the size, and that we can write to a file and dynamically expand the size. It also demonstrates that we can expand the number of sectors used, and that truncate will shorten the file and unallocate sectors dynamically.

### testAllocInode

Illustrates the use of allocInode for creating inode entries.

## waiter.py

![Oh yeah. It's all coming together.](./necessary%20assets/27d.jpg)

We've finally made it into the home stretch. `waiter.py` holds all of the functionallity necessary for running the lardfs system using FUSE. To a varying degree that is.

### Configuration

Looking at the `main` function, you can see we first parse in the command line arguments, and then set up options using those as well as initializing a logger. We then create an instance of `LardFS`, a class that extends `llfuse.Operations`. This is necessary for `llfuse.init`, which sets up and mounts our filesystem at the location specified by `options.mountpoint`. llfuse will then use our `LardFS` class to provide functionallity to system calls regarding any files in that mountpoint that are of the lardfs image type.

### LardFS

This class implements `llfuse.Operations`, which allows FUSE to look at this class for functionallity regarding the filesystem. We also initialize our `Image` class here to manage the disk version of the filesystem. One thing of note here is that we do `inode - 1` or `inode + 1` a lot throughout this system. The reason for that is that all the `Inode`s in `Image` are 0-based, and llfuse's inodes are 1-based.

#### flush and fsync

Given that our system is currently synchronous, both of these functions are no-ops.

#### Reading Directories

For reading directories, we need to implement the `opendir`, `readdir`, `releasedir`, `lookup`, and `getattr` functions. The `opendir` is in essence a no-op function, but it interacts with `readdir` in a fun way. as you can see, `opendir` returns an inode, which might seem a bit odd since `readdir` takes in a file handle. These two values are actually the same thing where `opendir` is supposed to be a verification of the file and `readdir` recieves the authenticated inode value. After that `readdir` uses `getattr` to actually read the related info, which uses `Image` to grab the correct `Inode` and populates a `llfuse.EntryAttributes` object. The `lookup` function is used for nested directories, where we're given the parent directory's inode and a name to match on and we're expected to find that entry and return the attributes of the entry. The name comparisons were a bit tricksy, but other than that pretty straight forward.

#### Reading Files

Reading files is much simpler than directories in my opinion. All we need for this is the `open`, `read`, and `release` calls. `open` and `release` are essentially no-ops for the same reason as directories. Reading files is made super easy due to the functionallity of `Image`, so we just call `readFile` and call it a day.
