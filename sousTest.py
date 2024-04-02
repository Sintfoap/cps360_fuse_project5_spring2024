from lardinator3000 import Image

def getImage():
    return Image(open("./lardfs.img", "rb+"))

def testRead():
    image = getImage()
    assert image.readFile(2).data.decode().strip() == "hello, world!"

def testWrite():
    image = getImage()
    assert image.readFile(2).data.decode().strip() == "hello, world!"
    assert image.iNodes[2].size == 14
    image.writeFile(2, 0, b"weelp")
    assert image.readFile(2).data.decode().strip() == "weelp, world!"
    image.writeFile(2, 7, b"thingy!\n")
    assert image.readFile(2).data.decode().strip() == "weelp, thingy!"
    assert image.iNodes[2].size == 15
    image.writeFile(2, 0, b"hello, world!\n")
    image.truncate(2, 14)
    assert len(image.getImaps(4)) == 3
    image.writeFile(4, 1337, b"A"*199)
    assert len(image.getImaps(4)) == 3
    image.writeFile(4, 1536, b"A")
    print(image.iNodes[4].size)
    assert len(image.getImaps(4)) == 4
    image.truncate(4, 1337)
    assert len(image.getImaps(4)) == 3

def testAllocInode():
    image = getImage()
    [print(inode) for inode in image.iNodes[:10]]
    assert len([inode for inode in image.iNodes if inode.mode != 0]) == 5
    image.allocInode(2)
    assert len([inode for inode in image.iNodes if inode.mode != 0]) == 6
    assert image.iNodes[5].mode == 2
    

if __name__ == "__main__":
    image = getImage()
    testWrite()
