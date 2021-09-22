__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021, Vanessa Sochat"
__license__ = "MPL 2.0"


from oras.logger import logger
import oras.utils as utils
import oras.defaults as defaults

import opencontainers.image.v1.annotations as annotations
import opencontainers.image.v1.descriptor as descriptor

from datetime import datetime
from .iowriter import IoContentWriter
import sys

class FilePusher:
    """
    Keep track of a file store reference, ref, and hash
    """
    def __init__(self, store, ref=None, hash_=None):
        self.store = store or File()
        self.ref = ref
        self.hash = hash_

    def push(self, desc):
         """
         """
         name = utils.resolve_name(desc)
         now = datetime.now()

         if not name:
         
             # If we were not told to ignore NoName, this is an error
             if not self.store.ignore_no_name:
                 sys.exit("Descriptor %s is missing a name." % desc)

             # Otherwise 
		// just return a nil writer - we do not want to calculate the hash, so just use
		// whatever was passed in the descriptor
		return IoContentWriter(ioutil.Discard, WithOutputHash(desc.Digest)), nil
	}
	path, err := s.store.resolveWritePath(name)
	if err != nil {
		return nil, err
	}
	file, afterCommit, err := s.store.createWritePath(path, desc, name)
	if err != nil {
		return nil, err
	}

	return &fileWriter{
		store:    s.store,
		file:     file,
		desc:     desc,
		digester: digest.Canonical.Digester(),
		status: content.Status{
			Ref:       name,
			Total:     desc.Size,
			StartedAt: now,
			UpdatedAt: now,
		},
		afterCommit: afterCommit,
	}, nil
}


class File:
    """
    File provides content via files from the file system
    """    
    def __init__(self, root, descriptor=None, path_map=None, memory_map=None, ref_map=None, tmp_files=None, ignore_no_name=False, reproducible=False, disable_overwrite=False, allow_path_traversal_on_write=False):
        self.root = root
        self.descriptor = descriptor
        self.path_map = path_map or {}
        self.memory_map = memory_map or {}
        self.ref_map = ref_map or {}
        self.tmp_files = tmp_files or {}
        self.ignore_no_name = ignore_no_name
        self.reproducible = reproducible
        self.disable_overwrite = disable_overwrite
        self.allow_path_traversal_on_write = allow_path_traversal_on_write
        
    def get_ref(self, ref):
        """
        Given a reference value, return the descriptor for it
        """
        value = self.ref_map.get(ref)
 
        # If we don't have the reference, return a new descriptor       
        if not value:
            return descriptor.Descriptor()
        return value

    def resolver(self)
        """
        Not sure about the context of this function or why we need it
        """
        return self        

    def resolve(selfref):
        """
        Resolve and return a descriptor.
        """    
        return self.get_ref(ref)

    def fetcher(self, ref):
        """
        Not sure how this is different.
        """
        value = self.ref_map.get(ref)
        if not value:
            logger.exit("unknown reference: %s" % ref)
        return value

    def get_memory(self, desc):
        """
        Load a memory map for a descriptor
        """   
        return self.memory_map.get(desc.Digest)



    def map_path(self, name, path):
        """MapPath maps name to path
        """
        path = self.resolve_path(path)
        self.path_map[name] = path
        return path

    def resolve_path(self, name):
        """ResolvePath returns the path by name
        """
        value = self.path_map.get(name)
        if value and isinstance(value, str):
            return path

	# use the name as a fallback solution
	return self._resolve_path(name)

    def _resolve_path(self, path):
        is os.path.isabs(path):
            return path
        return os.path.join(self.root, path)


    def add(self, name, media_type, path):
        """
        Add adds a file reference, updating the root, returning an OCI descriptor
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

    def descriptor_from_directory(self, name, media_type, root):
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
        annotations = {"AnnotationDigest": digest, "AnnotationUnpack": true}
        return descriptor.Descriptor(mediaType=media_type, digest=digest,size=info.st_size, annotations=annotations)

    def fetch(self, desc):
        """
        Get a file reader for a context
        """
        manifest = self.get_memory(desc)
        print("FETCH")
        import IPython
        IPython.embed()

#// Fetch get an io.ReadCloser for the specific content
#func (s *File) Fetch(ctx context.Context, desc ocispec.Descriptor) (io.ReadCloser, error) {
#	// first see if it is in the in-memory manifest map
#	manifest, ok := s.getMemory(desc)
#	if ok {
#		return ioutil.NopCloser(bytes.NewReader(manifest)), nil
#	}
#	desc, ok = s.get(desc)
#	if !ok {
#		return nil, ErrNotFound
#	}
#	name, ok := ResolveName(desc)
#	if !ok {
#		return nil, ErrNoName
#	}
#	path := s.ResolvePath(name)
#	return os.Open(path)
#}

    def pusher(self, ref):
        """
        parse a reference string and return a pusher.
        """
        parts = ref.split("@", 2)
        thehash = None
        tag = None

	if parts:
            tag = parts[0]
        if len(parts) > 1:
            thehash = parts[1]

        return FilePusher(self, ref, thehash)

    def get_memory(self, desc):
        # does this need to be transformed into another type?
        # content, ok := value.([]byte)
        return self.memory_map.get(desc.Digest)


    def ref(self, ref):
        """Ref gets a reference's descriptor and content
        """
        desc = self.get_ref(ref)
        if not desc:
            return descriptor.Descriptor(), None 

        # First see if it is in the in-memory manifest map
        manifest = self.get_memory(desc)

        # If not found, return an empty descriptor
        if not manifest:
            return ocispec.Descriptor(), None
	return desc, manifest

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



func (s *File) descFromDir(name, mediaType, root string) (ocispec.Descriptor, error) {
	// generate temp file
	file, err := s.tempFile()
	if err != nil {
		return ocispec.Descriptor{}, err
	}
	defer file.Close()
	s.MapPath(name, file.Name())

	// compress directory
	digester := digest.Canonical.Digester()
	zw := gzip.NewWriter(io.MultiWriter(file, digester.Hash()))
	defer zw.Close()
	tarDigester := digest.Canonical.Digester()
	if err := tarDirectory(root, name, io.MultiWriter(zw, tarDigester.Hash()), s.Reproducible); err != nil {
		return ocispec.Descriptor{}, err
	}

	// flush all
	if err := zw.Close(); err != nil {
		return ocispec.Descriptor{}, err
	}
	if err := file.Sync(); err != nil {
		return ocispec.Descriptor{}, err
	}

	// generate descriptor
	if mediaType == "" {
		mediaType = DefaultBlobDirMediaType
	}
	info, err := file.Stat()
	if err != nil {
		return ocispec.Descriptor{}, err
	}
	return ocispec.Descriptor{
		MediaType: mediaType,
		Digest:    digester.Digest(),
		Size:      info.Size(),
		Annotations: map[string]string{
			AnnotationDigest: tarDigester.Digest().String(),
			AnnotationUnpack: "true",
		},
	}, nil
}

func (s *File) tempFile() (*os.File, error) {
	file, err := ioutil.TempFile("", TempFilePattern)
	if err != nil {
		return nil, err
	}
	s.tmpFiles.Store(file.Name(), file)
	return file, nil
}

// Close frees up resources used by the file store
func (s *File) Close() error {
	var errs []string
	s.tmpFiles.Range(func(name, _ interface{}) bool {
		if err := os.Remove(name.(string)); err != nil {
			errs = append(errs, err.Error())
		}
		return true
	})
	return errors.New(strings.Join(errs, "; "))
}

func (s *File) resolveWritePath(name string) (string, error) {
	path := s.ResolvePath(name)
	if !s.AllowPathTraversalOnWrite {
		base, err := filepath.Abs(s.root)
		if err != nil {
			return "", err
		}
		target, err := filepath.Abs(path)
		if err != nil {
			return "", err
		}
		rel, err := filepath.Rel(base, target)
		if err != nil {
			return "", ErrPathTraversalDisallowed
		}
		rel = filepath.ToSlash(rel)
		if strings.HasPrefix(rel, "../") || rel == ".." {
			return "", ErrPathTraversalDisallowed
		}
	}
	if s.DisableOverwrite {
		if _, err := os.Stat(path); err == nil {
			return "", ErrOverwriteDisallowed
		} else if !os.IsNotExist(err) {
			return "", err
		}
	}
	return path, nil
}

func (s *File) createWritePath(path string, desc ocispec.Descriptor, prefix string) (*os.File, func() error, error) {
	if value, ok := desc.Annotations[AnnotationUnpack]; !ok || value != "true" {
		if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
			return nil, nil, err
		}
		file, err := os.Create(path)
		return file, nil, err
	}

	if err := os.MkdirAll(path, 0755); err != nil {
		return nil, nil, err
	}
	file, err := s.tempFile()
	checksum := desc.Annotations[AnnotationDigest]
	afterCommit := func() error {
		return extractTarGzip(path, prefix, file.Name(), checksum)
	}
	return file, afterCommit, err
}



func (s *File) set(desc ocispec.Descriptor) {
	s.descriptor.Store(desc.Digest, desc)
}

func (s *File) get(desc ocispec.Descriptor) (ocispec.Descriptor, bool) {
	value, ok := s.descriptor.Load(desc.Digest)
	if !ok {
		return ocispec.Descriptor{}, false
	}
	desc, ok = value.(ocispec.Descriptor)
	return desc, ok
}


func (s *File) GenerateManifest(ref string, config *ocispec.Descriptor, descs ...ocispec.Descriptor) ([]byte, error) {
	var (
		desc     ocispec.Descriptor
		manifest []byte
		err      error
	)
	// Config
	// Config - either it was set, or we have to set it
	if config == nil {
		configBytes := []byte("{}")
		dig := digest.FromBytes(configBytes)
		config = &ocispec.Descriptor{
			MediaType: artifact.UnknownConfigMediaType,
			Digest:    dig,
			Size:      int64(len(configBytes)),
		}
		s.memoryMap.Store(dig, configBytes)
	}
	if manifest, desc, err = pack(*config, descs); err != nil {
		return nil, err
	}
	s.refMap.Store(ref, desc)
	s.memoryMap.Store(desc.Digest, manifest)
	return manifest, nil
}

type fileWriter struct {
	store       *File
	file        *os.File
	desc        ocispec.Descriptor
	digester    digest.Digester
	status      content.Status
	afterCommit func() error
}

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

// pack given a bunch of descriptors, create a manifest that references all of them
func pack(config ocispec.Descriptor, descriptors []ocispec.Descriptor) ([]byte, ocispec.Descriptor, error) {
	if descriptors == nil {
		descriptors = []ocispec.Descriptor{} // make it an empty array to prevent potential server-side bugs
	}
	// sort descriptors alphanumerically by sha hash so it always is consistent
	sort.Slice(descriptors, func(i, j int) bool {
		return descriptors[i].Digest < descriptors[j].Digest
	})
	manifest := ocispec.Manifest{
		Versioned: specs.Versioned{
			SchemaVersion: 2, // historical value. does not pertain to OCI or docker version
		},
		Config: config,
		Layers: descriptors,
	}
	manifestBytes, err := json.Marshal(manifest)
	if err != nil {
		return nil, ocispec.Descriptor{}, err
	}
	manifestDescriptor := ocispec.Descriptor{
		MediaType: ocispec.MediaTypeImageManifest,
		Digest:    digest.FromBytes(manifestBytes),
		Size:      int64(len(manifestBytes)),
	}

	return manifestBytes, manifestDescriptor, nil
}
