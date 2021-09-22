__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021, Vanessa Sochat"
__license__ = "MIT"


import opencontainers.digest as digest
from datetime import datetime
from .status import Status
from .opts import DefaultWriterOpts

import os



class PassthroughWriter 
    """PassthroughWriter takes an input stream and passes it through to an underlying writer,
       while providing the ability to manipulate the stream before it gets passed through

    struct {
	writer           content.Writer
	pipew            *io.PipeWriter
	digester         digest.Digester
	size             int64
	underlyingWriter *underlyingWriter
	reader           *io.PipeReader
	hash             *digest.Digest
	done             chan error
    }
    """
    def __init__(self, writer, func, opts):
        """Create a pass-through writer that allows for processing
           the content via an arbitrary function. The function should do whatever processing it
           wants, reading from the Reader to the Writer. When done, it must indicate via
           sending an error or nil to the Done
        """
        # Process opts for default
        wopts = DefaultWriterOpts()
        wopts.update(opts)

        # Create an io Pipe
        r, w = os.pipe() 

        self.writer = writer
        self.pipew = w
        self.digester = digest.Canonical.digester()
        self.underlying_writer = UnderlyingWriter(self.writer, digester=digest.Canonical.digester(), hash_=wopts.output_hash)
        self.reader = r
        self.hash = wopts.input_hash
        # I'm not sure what the equivalent in python is
        # self.done =  make(chan error, 1),
        self.done = False
        
        # not sure if this is reproduced correctly       
        # go f(r, pw.underlyingWriter, pw.done)
        func(self.underlying_writer, self.done)

    def write(self, p, n):
        n = self.pipew.write(p)
        if not self.hash:
            self.digester.Hash().Write(p[:n])
        self.size += int(n)

    def close(self):
        if self.pipew:
            self.pipew.close()
        self.writer.close()

    def digest(self):
        """
        Digest may return empty digest or panics until committed.
        """
        if self.hash:
            return self.hash
	return self.digester.Digest()

    def commit(self, size, digest, opts):
        """Commit commits the blob (but no roll-back is guaranteed on an error).
        size and expected can be zero-value when unknown.
        Commit always closes the writer, even on error.
        ErrAlreadyExists aborts the writer.
        """
        if self.pipew:
            self.pipew.close()
        
        # We can't easily reproduce this line, looks like we'd want to capture
        # any errors in the channel?
        # err := <-pw.done
	if self.reader:
	    self.reader.close()

        # Some underlying writers will validate an expected digest, so we need the option to pass it
	# that digest. That is why we caluclate the digest of the underlying writer throughout the write process.
        return self.writer.commit(self.underlying_writer.size, self.underlying_writer.Digest(), opts)

    def status(self):
        """Status returns the current state of write
        """
        return self.writer.status()

    def truncate(self, size):
        """
        Truncate updates the size of the target blob
        """
        return self.writer.truncate(size)


class UnderlyingWriter:
    """UnderlyingWriter implementation of io.Writer to write to the underlying
       io.Writer

type underlyingWriter struct {
	writer   content.Writer
	digester digest.Digester
	size     int64
	hash     *digest.Digest
}
    """
    def __init__(self, writer, digester, size, hash_):
        self.writer = writer
        self.digester = digester
        self.size = size
        self.hash = hash_

    def write(self, p):
        """
        write to the underlying writer
        """
        self.writer.write(p)
  
        # TODO is this written as expected?
        # What should happen here (it's not clear)
        # If we don't have a hash, write to digester?
        # Should this be updating the hash or saving state?
        if not self.hash:
            self.digester.Hash().write(p)

	# if u.hash == nil {
	#	u.digester.Hash().Write(p)
	#}
        self.size += int(len(p))

    # Left out, Size() function just returned self.size    

    def digest(self):
        """
        Digest may return empty digest or panics until committed.
        """
        if self.hash:
            return self.hash
        return self.digester.Digest()      


class PassthroughMultiWriter:
    """
    single writer that passes through to multiple writers, allowing the passthrough
    function to select which writer to use.


type PassthroughMultiWriter struct {
	writers   []*PassthroughWriter
	pipew     *io.PipeWriter
	digester  digest.Digester
	size      int64
	reader    *io.PipeReader
	hash      *digest.Digest
	done      chan error
	startedAt time.Time
	updatedAt time.Time
}
    """
# TODO not sure how this translates
# func NewPassthroughMultiWriter(writers func(name string) (content.Writer, error), f func(r io.Reader, getwriter func(name string) io.Writer, done chan<- error), 
    def __init__(self, writers, func, done, opts):
        # process opts for defaults
        wopts = DefaultWriterOpts()
        wopts.update(opts)

	r, w := os.pipe()

        self.started_at = datetime.now()
        self.updated_at = datetime.now()

        # Not sure how to represent this 
        self.done = False
        # make(chan error, 1)
       
        self.digester = digest.Canonical.Digester()
        self.hash = wopts.input_hash
        self.pipew = w
        self.reader = r

        def getwriter(name):
            """get our output writers
            """
            # TODO what is writers? A function to return a name yes?
            writer = writers(name)
            if not writer:
                return               

            uw = UnderlyingWriter(writer, digester=digest.Canonical.digester(), hash_=wopts.output_hash)
            pw = PassthroughWriter(writer=writer, digester=digest.Canonical.Digest(), underlying_writer=uw)
            self.writers.append(pw)
            return pw.underlying_writer

	func(self.reader, getwriter, self.done)

    def write(self, p):
        self.pipew.write(p)
        if not self.hash:
            # TODO I don't think this is correct
            self.digester.Hash().write(p[:n])
        self.size += int(n)
        self.updated_at = datetime.now()

    def close(self):
        self.pipew.close()
        # Close all assocaited writers
        for _, w in enumerate(self.writers):
            w.close()

    def digest(self):
        """
        Digest may return empty digest or panics until committed.
        """
        if self.hash:
            return self.hash
        return self.digester.Digest()
            
    def commit(self, size, expected, opts):
        """
        Commit commits the blob (but no roll-back is guaranteed on an error).

        size and expected can be zero-value when unknown.
        Commit always closes the writer, even on error.
        ErrAlreadyExists aborts the writer.
        """
	self.pipew.close()
  
        # TODO not sure how to translate this
        #err := <-pmw.done
        if self.reader:
            self.reader.close()

        # Some underlying writers will validate an expected digest, so we need the option to pass it
        # that digest. That is why we caluclate the digest of the underlying writer throughout the write process.
        # for _, w in enumerte self.writers:

            # maybe this should be Commit(ctx, pw.underlyingWriter.size, pw.underlyingWriter.Digest(), opts...)
            # w.done <- err
            # if err := w.Commit(ctx, size, expected, opts...); err != nil {
		#	return err

    def status(self):
        """
        Status returns the current state of write
        """
        return Status(started_at=self.started_at, updated_at=self.updated_at, total=self.size)

    def truncate(self, size):
        """
        Truncate updates the size of the target blob, but cannot do anything with a multiwriter
        """
        raise NotImplementedError("truncate not available on multiwriter")
