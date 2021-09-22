__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021, Vanessa Sochat"
__license__ = "MIT"

from dataclasses import dataclass
from opencontainers.digest import Digest
import opencontainers.image.v1 as ocispec
from .const import DefaultBlocksize


@dataclass
class CdWriterOpts:
    """
    Writer opts as defined by ContainerD:
    https://github.com/containerd/containerd/blob/main/content/content.go#L155
    """
    ref: str
    desc: ocispec.descriptor.Descriptor


@dataclass
class WriterOpts:
    """
    Options for a Writer
    """
    input_hash: Digest
    output_hash: Digest
    block_size: int
    multi_writer_ingester: bool
    ignore_no_name: bool

    def update(self, opts):
        """
        Given another dataclass, update opts.       
        """
        if not isinstance(opts, WriterOpts):
            return
        for attr in opts:
            value = getattr(attr, None)
            if value is not None:
                setattr(self, attr, value)

    def __iter__(self):
        """
        Iter should yield the attributes names
        """
        for name in self.__dict__:
            yield name

# It wasn't clear what the default for multi_writer_ingester should be
def DefaultWriterOpts():
    return WriterOpts(None, None, DefaultBlocksize, False, True)
    
def with_input_hash(digest):
    """WithInputHash provide the expected input hash to a writer. Writers
    may suppress their own calculation of a hash on the stream, taking this
    hash instead. If the Writer processes the data before passing it on to another
    Writer layer, this is the hash of the *input* stream.
    To have a blank hash, use WithInputHash(BlankHash).
    """
    def func(opts):
        opts.input_hash = digest
    return func

def with_output_hash(digest)
    """WithOutputHash provide the expected output hash to a writer. Writers
    may suppress their own calculation of a hash on the stream, taking this
    hash instead. If the Writer processes the data before passing it on to another
    Writer layer, this is the hash of the *output* stream.
    To have a blank hash, use WithInputHash(BlankHash).
    """
    def func(opts):
        opts.output_hash = digest
    return func


def with_block_size(opts):
    """WithBlocksize set the blocksize used by the processor of data.
    The default is DefaultBlocksize, which is the same as that used by io.Copy.
    Includes a safety check to ensure the caller doesn't actively set it to <= 0.
    """
    def with_block_size(blocksize):
        def func(opts):
            if blocksize <= 0:
                sys.exit("blocksize must be greater than or equal to 0")
            opts.blocksize = blocksize

}

def with_multi_writer_ingester():
    """WithMultiWriterIngester the passed ingester also implements MultiWriter
    and should be used as such. If this is set to true, but the ingester does not
    implement MultiWriter, calling Writer should return an error.
    """
    def func(opts):
        opts.multi_writer_ingester = True

    # TODO test if we need to return the opts instead
    return func


def with_error_on_no_name():
    """WithErrorOnNoName some ingesters, when creating a Writer, do not return an error if
    the descriptor does not have a valid name on the descriptor. Passing WithErrorOnNoName
    tells the writer to return an error instead of passing the data to a nil writer.
    """
    def func(opts):
        opts.ignore_no_name = False
    return func

def with_ignore_no_name():
    """WithIgnoreNoName some ingesters, when creating a Writer, return an error if
    the descriptor does not have a valid name on the descriptor. Passing WithIgnoreNoName
    tells the writer not to return an error, but rather to pass the data to a nil writer.
    Deprecated: Use WithErrorOnNoName
    """
    def func(opts):
        opts.ignore_no_name = True
    return func
