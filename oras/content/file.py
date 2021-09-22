__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021, Vanessa Sochat"
__license__ = "MPL 2.0"


import os
import time
import tarfile
import tempfile
import time

from oras.logger import logger
import oras.utils as utils
import oras.defaults as defaults
from .const import TempFilePattern, AnnotationUnpack, AnnotationDigest
from .utils import resolve_name, tar_directory
from .readerat import sizeReaderAt
from .utils import tar_directory
from .opts import CdWriterOpts, WithOutputHash
from .iowriter import IoContentWriter

import opencontainers.image.v1.annotations as annotations
import opencontainers.image.v1.descriptor as descriptor


class FileStore:
    """
    A FileStore provides content from the file system
    """
    def __init__(self, **kwargs):
        self.root = kwargs.get("root")
        self.descriptor = kwargs.get('descriptor', {})
        self.path_map = kwargs.get("path_map", {})
        self.tmp_files = kwargs.get("tmp_files", {})
        self.ignore_no_name = kwargs.get("ignore_no_name", False)

        self.disable_overwrite = kwargs.get("disable_overwrite", False)
        self.allow_path_traversal_on_write = kwargs.get("allow_path_traversal_on_write", False)
        self.reproducible = kwargs.get("reproducible", False)
      

    def map_path(self, name, path):
        """
        Map a name to a path
        """
        path = self.resolve_path(path)
        self.path_map[name] = path
        return path      

   def resolve_path(self, name):
       """
       Return the path by name
       """
       path = self.path_map.get(name)
       if path or (path and os.path.isabs(path)):
           return path
       return os.path.join(self.root, path)


    def set(self, desc):
        """
        Save a descriptor to the map.
        """
        self.descriptor[desc.Digest.value] = desc


    def add(self, name, media_type, path):
        """
        Add a file reference
        """
        path = path or name
        path = self.map_path(name, path)

        if os.path.isdir(path):
            desc = self.descriptor_from_dir(name, media_type, path)
        elif os.path.isfile(path):
            desc = self.descriptor_from_file(media_type, path)
        else:
            logger.exit("%s is not a valid path." % path)
	desc.Annotations[annotations.AnnotationTitle] = name

	self.set(desc)
	return desc


    def descriptor_from_file(self, media_type, path):
        """
        Get a descriptor from file.
        """
        if not os.path.exists(path):
            logger.exit("%s does not exist." % path)
    
        try:
            digest = utils.get_file_hash(path)
        except:
            logger.exit("Cannot calculate digest for %s" % path)

        if not media_type:
            media_type = defaults.DefaultBlobMediaType

        stat = os.stat(path)
        return descriptor.Descriptor(mediaType=media_type, digest=digest, size=stat.st_size)

    def descriptor_from_dir(self, name, media_type, root):
        """
        Get a descriptor from a director
        """
        name = self.map_path(name, tmpfie)

        # Compress directory to tmpfile
        tar = tar_directory(root, name, strip_times=self.reproducible)
        
        # Get digest
        digest = "sha256:%s" % utils.get_file_hash(tar)
        
        # generate descriptor
        if not media_type:
            media_type = defaults.DefaultBlobMediaType

        info = os.stat(tar)
         
        # Question: what is the difference between AnnotationDigest and digest?
        annotations = {"AnnotationDigest": digest, "AnnotationUnpack": True}
        return descriptor.Descriptor(mediaType=media_type, digest=digest,size=info.st_size, annotations=annotations)


    def temp_file(self):
        """
        Create and store a temporary file
        """
        filen = tempfile.NamedTemporaryFile(prefix=TempFilePattern)
        self.tmp_files[filen.name] = filen
        return filen

    def close(self):
        """Close frees up resources used by the file store
        """
        for name, filen in self.tmp_files.items():
            filen.close()
            if os.path.exists(name):
                os.remove(name)

    def set(self, desc):
        """
        Set an OCI descriptor
        """
        self.descriptor[desc.Digest] = desc        

    def get(desc):
        """
        Get an OCI descriptor
        """
        value = self.descriptor.get(desc.Digest)
        if not value:
            return descriptor.Descriptor()
        return value

    def reader_at(self, desc):
        """ReaderAt provides contents
        """
        desc = self.get(desc)
        if not desc:
            sys.exit("Could not find descriptor.")

        name = resolve_name(desc)
        if not name:
            sys.exit("Cannot resolve name for %s" % desc)  
        
        path = self.resolve_path(name)
        fileo = open(path, 'r') 
        return sizeReaderAt(fileo, desc.size)


    def writer(self, opts):
        """Writer begins or resumes the active writer identified by desc
        """
        wopts = CdWriterOpts()
        wopts.update(opts)
        desc = wopts.Desc
        name = resolve_name(desc)

        # if we were not told to ignore NoName, then return an error
        if not name and not self.ignore_no_name:
            sys.exit("Cannot resolve name for %s" % desc)  
        elif not name and self.ignore_no_name:
            # just return a nil writer - we do not want to calculate the hash, so just use
            # whatever was passed in the descriptor
            return IoContentWriter(WithOutputHash(desc.Digest)

        path = self.resolve_write_path(name)

        filen, after_commit = self.create_write_path(path, desc, name)
        now = time.time()

        # STOPPED HERE need to find content.Status
        status =
		status: content.Status{
			Ref:       name,
			Total:     desc.Size,
			StartedAt: now,
			UpdatedAt: now,
		},

       
        return FileWriter(store=self, fileh=filen, desc=desc, status=status, after_commit=after_commit)


    def resolve_write_path(self, name):
        """Resolve the write path
        """
        path = self.resolve_path(name)
        if not self.allow_path_traversal_on_write:
            base = os.path.abspath(self.root)
            target = os.path.abspath(path)
            rel = os.path.relpath(base, target)
            if rel.startswith("../") or rel == "..":
                return ""

        if self.disable_overwrite:

            print("NEED TO CHECK OVERWRITE")
            # TODO what do we want to check here, if writable?
            #if os.stat(path)
            # if _, err := os.Stat(path); err == nil {
            # return "", ErrOverwriteDisallowed
            # } else if !os.IsNotExist(err) {
            # return "", err
        return path

    def create_write_path(self, path, desc, prefix):
        """
        Create a write path?
        """
        value = desc.Annotations.get(AnnotationUnpack)
        if not value:
            os.makedirs(os.path.dirname(path))
            with open(path, 'w') as fd:
                pass
            return filen, None

        os.makedirs(path)
        filen = tempfile.mkstemp()[1] 
        checksum = desc.Annotations.get(AnnotationDigest) 
        
        def after_commit():
            return extract_tar_gzip(path, prefix, filen, checksum)
	return filen, after_commit


class FileWriter:

    def __init__(self, store, fileh, desc, status, after_commit, digester=None):
        self.store = store                # *FileStore
        self.file = fileh                 # *os.File
        self.desc = desc                  # ocispec.Descriptor
        self.status = status              # content.Status
        self.after_commit = after_commit  # func()
        self.digester = digester or digest.Canonical.Digester() # TODO what is this?

func (w *fileWriter) Status() (content.Status, error) {
	return w.status, nil
}

// Digest returns the current digest of the content, up to the current write.
//
// Cannot be called concurrently with `Write`.
func (w *fileWriter) Digest() digest.Digest {
	return w.digester.Digest()
}

// Write p to the transaction.
func (w *fileWriter) Write(p []byte) (n int, err error) {
	n, err = w.file.Write(p)
	w.digester.Hash().Write(p[:n])
	w.status.Offset += int64(len(p))
	w.status.UpdatedAt = time.Now()
	return n, err
}

func (w *fileWriter) Commit(ctx context.Context, size int64, expected digest.Digest, opts ...content.Opt) error {
	var base content.Info
	for _, opt := range opts {
		if err := opt(&base); err != nil {
			return err
		}
	}

	if w.file == nil {
		return errors.Wrap(errdefs.ErrFailedPrecondition, "cannot commit on closed writer")
	}
	file := w.file
	w.file = nil

	if err := file.Sync(); err != nil {
		file.Close()
		return errors.Wrap(err, "sync failed")
	}

	fileInfo, err := file.Stat()
	if err != nil {
		file.Close()
		return errors.Wrap(err, "stat failed")
	}
	if err := file.Close(); err != nil {
		return errors.Wrap(err, "failed to close file")
	}

	if size > 0 && size != fileInfo.Size() {
		return errors.Wrapf(errdefs.ErrFailedPrecondition, "unexpected commit size %d, expected %d", fileInfo.Size(), size)
	}
	if dgst := w.digester.Digest(); expected != "" && expected != dgst {
		return errors.Wrapf(errdefs.ErrFailedPrecondition, "unexpected commit digest %s, expected %s", dgst, expected)
	}

	w.store.set(w.desc)
	if w.afterCommit != nil {
		return w.afterCommit()
	}
	return nil
}

// Close the writer, flushing any unwritten data and leaving the progress in
// tact.
func (w *fileWriter) Close() error {
	if w.file == nil {
		return nil
	}

	w.file.Sync()
	err := w.file.Close()
	w.file = nil
	return err
}

func (w *fileWriter) Truncate(size int64) error {
	if size != 0 {
		return ErrUnsupportedSize
	}
	w.status.Offset = 0
	w.digester.Hash().Reset()
	if _, err := w.file.Seek(0, io.SeekStart); err != nil {
		return err
	}
	return w.file.Truncate(0)
}
