__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021, Vanessa Sochat"
__license__ = "MPL 2.0"


from oras.logger import logger
import oras.utils as utils
import oras.defaults as defaults

import opencontainers.image.v1.annotations as annotations
import opencontainers.image.v1.descriptor as descriptor

from datetime import datetime
import sys


import (
	"io"

	"github.com/containerd/containerd/content"
)

## stopped looking at https://github.com/containerd/containerd/blob/f0a32c66dad1e9de716c9960af806105d691cd78/content/content.go
## how much do we need to reproduce?

// ensure interface
var (
	_ content.ReaderAt = sizeReaderAt{}
)

type readAtCloser interface {
	io.ReaderAt
	io.Closer
}

type sizeReaderAt struct {
	readAtCloser
	size int64
}

func (ra sizeReaderAt) Size() int64 {
	return ra.size
}

func NopCloserAt(r io.ReaderAt) nopCloserAt {
	return nopCloserAt{r}
}

type nopCloserAt struct {
	io.ReaderAt
}

func (n nopCloserAt) Close() error {
	return nil
}

// readerAtWrapper wraps a ReaderAt to give a Reader
type ReaderAtWrapper struct {
	offset   int64
	readerAt io.ReaderAt
}

func (r *ReaderAtWrapper) Read(p []byte) (n int, err error) {
	n, err = r.readerAt.ReadAt(p, r.offset)
	r.offset += int64(n)
	return
}

func NewReaderAtWrapper(readerAt io.ReaderAt) *ReaderAtWrapper {
	return &ReaderAtWrapper{readerAt: readerAt}
}
