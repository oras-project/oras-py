__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021, Vanessa Sochat"
__license__ = "MIT"

import os
import sys
from .opts import DefaultWriterOpts
import opencontainers.digest as digest

class IoContentWriter:
    """IoContentWriter writer that wraps an io.Writer, so the results can be streamed to
       an open io.Writer. For example, can be used to pull a layer and write it to a file, or device.

type IoContentWriter struct {
	writer   io.Writer
	digester digest.Digester
	size     int64
	hash     *digest.Digest
}
    """

    def __init__(self, writer=None, opts=None):
        """Create  new IoContentWriter

        Opts should be a dataclass for WriterOpts
        By default, it calculates the hash when writing. If the option `skipHash` is true,
        it will skip doing the hash. Skipping the hash is intended to be used only
        if you are confident about the validity of the data being passed to the writer,
        and wish to save on the hashing time.
        """        
        if not writer:
            writer = open(os.devnull,"w")

        # Create new writer options
        wopts = DefaultWriterOpts()
        wopts.update(opts or {})
 
        # Create an IoContentWriter        
        self.writer = writer
        self.digester = digest.Canonical.digester()

        # Take the output hash, since input hash goes to the passthrough writer
        # which then passes the processed output to us
        self.hash = wopts.output_hash

	return NewPassthroughWriter(ioc, func(r io.Reader, w io.Writer, done chan<- error) {
		// write out the data to the io writer
		var (
			err error
		)
		// we could use io.Copy, but calling it with the default blocksize is identical to
		// io.CopyBuffer. Otherwise, we would need some way to let the user flag "I want to use
		// io.Copy", when it should not matter to them
		b := make([]byte, wOpts.Blocksize, wOpts.Blocksize)
		_, err = io.CopyBuffer(w, r, b)
		done <- err
	}, opts...)
}

func (w *IoContentWriter) Write(p []byte) (n int, err error) {
	n, err = w.writer.Write(p)
	if err != nil {
		return 0, err
	}
	w.size += int64(n)
	if w.hash == nil {
		w.digester.Hash().Write(p[:n])
	}
	return
}

func (w *IoContentWriter) Close() error {
	return nil
}

// Digest may return empty digest or panics until committed.
func (w *IoContentWriter) Digest() digest.Digest {
	return w.digester.Digest()
}

// Commit commits the blob (but no roll-back is guaranteed on an error).
// size and expected can be zero-value when unknown.
// Commit always closes the writer, even on error.
// ErrAlreadyExists aborts the writer.
func (w *IoContentWriter) Commit(ctx context.Context, size int64, expected digest.Digest, opts ...content.Opt) error {
	return nil
}

// Status returns the current state of write
func (w *IoContentWriter) Status() (content.Status, error) {
	return content.Status{}, nil
}

// Truncate updates the size of the target blob
func (w *IoContentWriter) Truncate(size int64) error {
	return nil
}

