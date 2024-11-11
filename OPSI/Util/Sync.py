# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0

# forked from: https://pypi.python.org/pypi/python-librsync/0.1-5
# inspiration: https://github.com/dvas0004/py_rdiff
# librsync in c: http://rproxy.samba.org/doxygen/librsync/refman.pdf
# notes: https://docs.python.org/2/library/ctypes.html

import base64
import ctypes
import ctypes.util
import os
import tempfile

from opsicommon.logging import get_logger

from OPSI.Types import forceFilename, forceUnicode

logger = get_logger("opsi.general")
_librsync = None

if os.name == "posix":
	path = ctypes.util.find_library("rsync")
	if path is None:
		raise ImportError("Could not find librsync, make sure it is installed")
	try:
		_librsync = ctypes.cdll.LoadLibrary(path)
	except OSError as err:
		raise ImportError(f"Could not load librsync at '{path}'") from err
elif os.name == "nt":
	try:
		_librsync = ctypes.cdll.librsync
	except Exception as err:
		raise ImportError("Could not load librsync, make sure it is installed") from err
else:
	raise NotImplementedError("Librsync is not supported on your platform")

MAX_SPOOL = 1024**2 * 5

RS_DONE = 0
RS_BLOCKED = 1

RS_JOB_BLOCKSIZE = 65536
RS_DEFAULT_STRONG_LEN = 8
RS_DEFAULT_BLOCK_LEN = 2048
RS_MD4_SIG_MAGIC = 0x72730136


#############################
#  DEFINES FROM librsync.h  #
#############################


# librsync.h: rs_buffers_s
class Buffer(ctypes.Structure):
	_fields_ = [
		("next_in", ctypes.c_char_p),
		("avail_in", ctypes.c_size_t),
		("eof_in", ctypes.c_int),
		("next_out", ctypes.c_char_p),
		("avail_out", ctypes.c_size_t),
	]


# char const *rs_strerror(rs_result r);
_librsync.rs_strerror.restype = ctypes.c_char_p
_librsync.rs_strerror.argtypes = (ctypes.c_int,)

# rs_job_t *rs_sig_begin(size_t new_block_len, size_t strong_sum_len);
_librsync.rs_sig_begin.restype = ctypes.c_void_p
_librsync.rs_sig_begin.argtypes = (
	ctypes.c_size_t,
	ctypes.c_size_t,
)

# rs_job_t *rs_loadsig_begin(rs_signature_t **);
_librsync.rs_loadsig_begin.restype = ctypes.c_void_p
_librsync.rs_loadsig_begin.argtypes = (ctypes.c_void_p,)

# rs_job_t *rs_delta_begin(rs_signature_t *);
_librsync.rs_delta_begin.restype = ctypes.c_void_p
_librsync.rs_delta_begin.argtypes = (ctypes.c_void_p,)

# rs_job_t *rs_patch_begin(rs_copy_cb *, void *copy_arg);
_librsync.rs_patch_begin.restype = ctypes.c_void_p
_librsync.rs_patch_begin.argtypes = (
	ctypes.c_void_p,
	ctypes.c_void_p,
)

# rs_result rs_build_hash_table(rs_signature_t* sums);
_librsync.rs_build_hash_table.restype = ctypes.c_size_t
_librsync.rs_build_hash_table.argtypes = (ctypes.c_void_p,)

# rs_result rs_job_iter(rs_job_t *, rs_buffers_t *);
_librsync.rs_job_iter.restype = ctypes.c_int
_librsync.rs_job_iter.argtypes = (
	ctypes.c_void_p,
	ctypes.c_void_p,
)

# void rs_trace_set_level(rs_loglevel level);
_librsync.rs_trace_set_level.restype = None
_librsync.rs_trace_set_level.argtypes = (ctypes.c_int,)

# void rs_free_sumset(rs_signature_t *);
_librsync.rs_free_sumset.restype = None
_librsync.rs_free_sumset.argtypes = (ctypes.c_void_p,)

# rs_result rs_job_free(rs_job_t *);
_librsync.rs_job_free.restype = ctypes.c_int
_librsync.rs_job_free.argtypes = (ctypes.c_void_p,)

# A function declaration for our read callback.
patch_callback = ctypes.CFUNCTYPE(
	ctypes.c_int,
	ctypes.c_void_p,
	ctypes.c_longlong,
	ctypes.c_size_t,
	ctypes.POINTER(Buffer),
)


class LibrsyncError(Exception):
	def __init__(self, r):
		super(LibrsyncError, self).__init__(_librsync.rs_strerror(ctypes.c_int(r)))


def _execute(job, input_handle, output_handle=None):
	"""
	Executes a librsync "job" by reading bytes from `input_handle` and writing results to
	`output_handle` if provided. If `output_handle` is omitted, the output is ignored.
	"""
	# Re-use the same buffer for output, we will read from it after each
	# iteration.
	out = ctypes.create_string_buffer(RS_JOB_BLOCKSIZE)
	while True:
		block = input_handle.read(RS_JOB_BLOCKSIZE)
		buff = Buffer()
		# provide the data block via input buffer.
		buff.next_in = ctypes.c_char_p(block)  # pylint: disable=attribute-defined-outside-init
		buff.avail_in = ctypes.c_size_t(len(block))  # pylint: disable=attribute-defined-outside-init
		buff.eof_in = ctypes.c_int(not block)  # pylint: disable=attribute-defined-outside-init
		# Set up our buffer for output.
		buff.next_out = ctypes.cast(out, ctypes.c_char_p)  # pylint: disable=attribute-defined-outside-init
		buff.avail_out = ctypes.c_size_t(RS_JOB_BLOCKSIZE)  # pylint: disable=attribute-defined-outside-init
		res = _librsync.rs_job_iter(job, ctypes.byref(buff))
		if output_handle:
			output_handle.write(out.raw[: RS_JOB_BLOCKSIZE - buff.avail_out])
		if res == RS_DONE:
			break
		if res != RS_BLOCKED:
			raise LibrsyncError(res)
		if buff.avail_in > 0:
			# There is data left in the input buffer, librsync did not consume
			# all of it. Rewind the file a bit so we include that data in our
			# next read. It would be better to simply tack data to the end of
			# this buffer, but that is very difficult in Python.
			input_handle.seek(input_handle.tell() - buff.avail_in)
	if output_handle and callable(getattr(output_handle, "seek", None)):
		# As a matter of convenience, rewind the output file.
		output_handle.seek(0)
	return output_handle


def librsyncSignature(filename, base64Encoded=True):
	"""
	Get the signature of the file to patch.
	"""
	logger.debug("Creating librsync signature of %s", filename)
	filename = forceFilename(filename)

	try:
		with open(filename, "rb") as filehandle:
			sigfile_handle = tempfile.SpooledTemporaryFile(
				max_size=MAX_SPOOL, mode="wb+"
			)

			job = None
			if hasattr(_librsync, "RS_DEFAULT_STRONG_LEN"):
				# librsync < 1.0.0
				job = _librsync.rs_sig_begin(
					RS_DEFAULT_BLOCK_LEN, RS_DEFAULT_STRONG_LEN
				)
			else:
				# librsync >= 1.0.0
				job = _librsync.rs_sig_begin(
					RS_DEFAULT_BLOCK_LEN, RS_DEFAULT_STRONG_LEN, RS_MD4_SIG_MAGIC
				)
			try:
				_execute(job, filehandle, sigfile_handle)
				sigfile_handle.seek(0)
				if base64Encoded:
					return base64.encodebytes(sigfile_handle.read()).decode("ascii")
				return sigfile_handle.read()
			finally:
				_librsync.rs_job_free(job)
				sigfile_handle.close()
	except Exception as sigError:
		raise RuntimeError(
			f"Failed to get librsync signature from {filename}: {forceUnicode(sigError)}"
		) from sigError


def librsyncDeltaFile(filename, signature, deltafile):
	"""
	Create delta file from original file and the signature of the file to patch.
	"""
	logger.debug("Creating librsync deltafile %s on base of %s", deltafile, filename)
	filename = forceFilename(filename)
	deltafile = forceFilename(deltafile)
	if filename == deltafile:
		raise ValueError("filename and deltafile are the same file")

	try:
		sigfile_handle = tempfile.NamedTemporaryFile("wb+")
		sigfile_handle.write(signature)
		sigfile_handle.seek(0)

		sig = ctypes.c_void_p()
		try:
			job = _librsync.rs_loadsig_begin(ctypes.byref(sig))
			try:
				_execute(job, sigfile_handle)
			finally:
				_librsync.rs_job_free(job)
			res = _librsync.rs_build_hash_table(sig)
			if res != RS_DONE:
				raise LibrsyncError(res)

			with open(filename, "rb") as filehandle:
				with open(deltafile, "wb") as deltafile_handle:
					job = _librsync.rs_delta_begin(sig)
					try:
						_execute(job, filehandle, deltafile_handle)

					finally:
						_librsync.rs_job_free(job)
		finally:
			sigfile_handle.close()
			_librsync.rs_free_sumset(sig)

	except Exception as sigError:
		raise RuntimeError(
			f"Failed to write delta file {deltafile}: {forceUnicode(sigError)}"
		) from sigError


def librsyncPatchFile(oldfile, deltafile, newfile):
	"""
	Create the new file from old file and delta file.
	"""

	logger.debug(
		"Patching with librync: old file %s, delta file %s, new file %s",
		oldfile,
		deltafile,
		newfile,
	)
	oldfile = forceFilename(oldfile)
	newfile = forceFilename(newfile)
	deltafile = forceFilename(deltafile)
	if oldfile == newfile:
		raise ValueError("oldfile and newfile are the same file")
	if deltafile == newfile:
		raise ValueError("deltafile and newfile are the same file")
	if deltafile == oldfile:
		raise ValueError("oldfile and deltafile are the same file")

	try:
		with open(oldfile, "rb") as oldfile_handle:

			@patch_callback
			def read_cb(opaque, pos, length, buff):
				oldfile_handle.seek(pos)
				size_p = ctypes.cast(length, ctypes.POINTER(ctypes.c_size_t)).contents
				size = size_p.value
				block = oldfile_handle.read(size)
				size_p.value = len(block)
				buff_p = ctypes.cast(buff, ctypes.POINTER(ctypes.c_char_p)).contents
				buff_p.value = block
				return RS_DONE

			with open(deltafile, "rb") as deltafile_handle:
				with open(newfile, "wb") as newfile_handle:
					job = _librsync.rs_patch_begin(read_cb, None)
					try:
						_execute(job, deltafile_handle, newfile_handle)
					finally:
						_librsync.rs_job_free(job)
	except Exception as patchError:
		raise RuntimeError(
			f"Failed to patch file {oldfile}: {forceUnicode(patchError)}"
		) from patchError
