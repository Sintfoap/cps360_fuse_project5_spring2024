#!/usr/bin/env python
from __future__ import annotations
import argparse
import logging
import sys
from typing import BinaryIO

import llfuse

LOG = logging.getLogger(__name__)

class LardFS:
    def __init__(self, image_file: BinaryIO):
        raise NotImplementedError()


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

    fuse_options = set(llfuse.default_options)
    fuse_options.add('fsname=lardfs')

    if options.debug_fuse:
        fuse_options.add('debug')

    llfuse.init(lardfs, options.mountpoint, fuse_options)
    try:
        llfuse.main(workers=1)
    except:
        llfuse.close(unmount=False)
        raise
    llfuse.close()


if __name__ == '__main__':
    main(sys.argv)

