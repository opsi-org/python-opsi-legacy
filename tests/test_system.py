# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing functionality of OPSI.System
"""

import os
import pytest
import shutil

from OPSI.System import copy
from OPSI.Util.Message import ProgressSubject


@pytest.fixture(
	params=[None, ProgressSubject(id="copy_test", title="Copy test")],
	ids=["non-tracking", "progresstracking"],
)
def progressSubject(request):
	yield request.param


@pytest.fixture(scope="session")
def exampleFilenames():
	return ("file1", "file2", "file3")


@pytest.fixture(scope="session")
def exampleDirectories():
	return ("dir1", "dir2", "dir3")


@pytest.fixture
def srcDir(tempDir):
	path = os.path.join(tempDir, "src")
	os.mkdir(path)
	return path


@pytest.fixture
def dstDir(tempDir):
	path = os.path.join(tempDir, "dst")
	os.mkdir(path)
	return path


@pytest.fixture
def filledSourceDirectory(srcDir, exampleFilenames, exampleDirectories):
	return fillDirectoryWithFilesAndFolders(
		srcDir, exampleFilenames, exampleDirectories
	)


def fillDirectoryWithFilesAndFolders(sourceDirectory, filenames, directories):
	fileContent = "x" * 10 * 1024

	for filename in filenames:
		pathToFile = os.path.join(sourceDirectory, filename)
		with open(pathToFile, "w") as outputFile:
			outputFile.write(fileContent)

	for dirname in directories:
		pathToDir = os.path.join(sourceDirectory, dirname)
		os.mkdir(pathToDir)

		for filename in filenames:
			pathToFile = os.path.join(pathToDir, filename)
			with open(pathToFile, "w") as outputFile:
				outputFile.write(fileContent)

	return sourceDirectory


def makeSureFilesAndFoldersExistAtDestination(
	filenames, directories, sourceDirectory, destinationDirectory
):
	bname = os.path.basename(sourceDirectory)
	for filename in filenames:
		pathToFile = os.path.join(destinationDirectory, bname, filename)
		assert os.path.isfile(pathToFile)

	for dirname in directories:
		pathToDir = os.path.join(destinationDirectory, bname, dirname)
		assert os.path.isdir(pathToDir)

		for filename in filenames:
			pathToFile = os.path.join(pathToDir, filename)
			assert os.path.isfile(pathToFile)


def makeSureFilesAndFoldersExistAtDestinationWithoutLongPath(
	filenames, directories, destinationDirectory
):
	"""
	Checking method for files and folders that does nut include the basename
	of the source directory.
	"""
	for filename in filenames:
		absPath = os.path.join(destinationDirectory, filename)
		assert os.path.isfile(absPath)

	for dirname in directories:
		fullDirPath = os.path.join(destinationDirectory, dirname)
		assert os.path.isdir(fullDirPath)

		for filename in filenames:
			filePath = os.path.join(fullDirPath, filename)
			assert os.path.isfile(filePath)


def testCopyingFromFileToFileOverwritesDestination(progressSubject, srcDir, dstDir):
	srcfile = os.path.join(srcDir, "testfile")
	with open(srcfile, "w") as f:
		f.write("new")

	dstfile = os.path.join(dstDir, "testfile")
	with open(dstfile, "w") as f:
		f.write("old")

	copy(srcfile, dstfile, progressSubject)

	with open(dstfile) as f:
		data = f.read()

	assert "new" == data


def testCopyingFromFileToDirectory(progressSubject, srcDir, dstDir):
	# src = file,  dst = dir			=> copy into dst
	srcfile = os.path.join(srcDir, "testfile")
	dstfile = os.path.join(dstDir, "testfile2")

	with open(srcfile, "w") as f:
		f.write("new")

	copy(srcfile, dstfile, progressSubject)

	with open(dstfile) as f:
		data = f.read()

	assert "new" == data


def testCopyingFromFileToNonExistingDestination(progressSubject, srcDir, dstDir):
	# src = file,  dst = not existent   => create dst directories, copy src to dst
	srcfile = os.path.join(srcDir, "testfile")
	dstfile = os.path.join(dstDir, "newdir", "testfile")

	with open(srcfile, "w") as f:
		f.write("new")

	copy(srcfile, dstfile, progressSubject)

	with open(dstfile) as f:
		data = f.read()

	assert "new" == data


def testCopyingFromDirectoryToFileRaisesException(progressSubject, srcDir, dstDir):
	# src = dir,   dst = file		   => error
	testSrcDir = os.path.join(srcDir, "testdir")
	os.makedirs(testSrcDir)

	testDstDir = os.path.join(dstDir, "testdir")
	with open(testDstDir, "w"):
		pass

	with pytest.raises(OSError):
		copy(testSrcDir, testDstDir, progressSubject)


def testCopyingFromDirectoryToDirectoryCopiesContent(
	progressSubject, filledSourceDirectory, dstDir, exampleFilenames, exampleDirectories
):
	# src = dir,   dst = dir			=> copy src dir into dst
	copy(filledSourceDirectory, dstDir, progressSubject)
	makeSureFilesAndFoldersExistAtDestination(
		exampleFilenames, exampleDirectories, filledSourceDirectory, dstDir
	)

	copy(filledSourceDirectory, dstDir, progressSubject)

	for name in os.listdir(
		os.path.join(dstDir, os.path.basename(filledSourceDirectory))
	):
		assert name in exampleDirectories + exampleFilenames

	for dirname in exampleDirectories:
		a = os.path.join(dstDir, os.path.basename(filledSourceDirectory), dirname)
		for name in os.listdir(a):
			assert name in exampleFilenames


def testCopyingFromDirectoryToNonExistingCreatesFolderAndCopiesContent(
	progressSubject, filledSourceDirectory, dstDir, exampleFilenames, exampleDirectories
):
	# src = dir,   dst = not existent   => create dst, copy content of src into dst
	shutil.rmtree(dstDir)
	copy(filledSourceDirectory, dstDir, progressSubject)

	makeSureFilesAndFoldersExistAtDestinationWithoutLongPath(
		exampleFilenames, exampleDirectories, dstDir
	)


def testCopyingManyFilesIntoNonFileDestination(
	progressSubject, filledSourceDirectory, dstDir, exampleFilenames, exampleDirectories
):
	# src = dir/*, dst = not file	   => create dst if not exists, copy content of src into dst
	copy(filledSourceDirectory + "/*.*", dstDir, progressSubject)

	makeSureFilesAndFoldersExistAtDestinationWithoutLongPath(
		exampleFilenames, exampleDirectories, dstDir
	)


def testCopyingFilesWithWildcardPattern(
	progressSubject, filledSourceDirectory, dstDir, exampleFilenames, exampleDirectories
):
	copy(filledSourceDirectory + "/*", dstDir, progressSubject)

	makeSureFilesAndFoldersExistAtDestinationWithoutLongPath(
		exampleFilenames, exampleDirectories, dstDir
	)


def testCopyingFilesWithWildcardPatternIncludingDot(
	progressSubject, filledSourceDirectory, dstDir, exampleFilenames, exampleDirectories
):
	copy(filledSourceDirectory + "/*.*", dstDir, progressSubject)

	makeSureFilesAndFoldersExistAtDestinationWithoutLongPath(
		exampleFilenames, exampleDirectories, dstDir
	)
