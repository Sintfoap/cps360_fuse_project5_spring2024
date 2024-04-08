# Fuse Project Report
## Author: Edward Taylor (etayl261)
Time spent: 31 hours

### Thoughts and reflections
I primarily worked on inode things and file operations such as the linking system, rename, etc. It was really fun, I really like this project, and I hope future generations of the OS class enjoy it too. Some personal thoughts about the project, it took me a little bit to understand, mostly the imaps, but once Moffit talked me through it, everything made sense. 

##### linking
Some things I got delayed by, I didn't really understand what hard links and symlinks were under the hood, so I might include an explanation for those in the project description. I would probably also mention that readlink needs to be implemented in order for the link system to work properly. 

##### fuse parameters
Another thing that really delayed both Moffit and I, sometimes it's unclear what is being passed in by the fuse library. For instance, some places where it passes in an inode, it's passing in the byte string of a name, and other places it's passing in the inode number. The fact that the inodes are a count from 1 instead of 0 is also confusing, and where it passed in mode bits, they do not include the file type, unlike the lard system. Some function prototypes defined in the starting project file or the description would certainly be helpful. 

##### Teammate 
Also, it was a pleasure working with Moffit, he's very quick to respond when I ask him questions, and also he put in a considerably larger amount of time than I was able to for this project. Without him I probably would not have been able to hit the stretch goals like we did. Thanks for letting us work this project, it was one of my favorites to date.
