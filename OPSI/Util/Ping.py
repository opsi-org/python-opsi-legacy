# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
A pure python ping implementation using raw socket.


Note that ICMP messages can only be sent from processes running as root.


Derived from ping.c distributed in Linux's netkit. That code is
copyright (c) 1989 by The Regents of the University of California.
That code is in turn derived from code written by Mike Muuss of the
US Army Ballistic Research Laboratory in December, 1983 and
placed in the public domain. They have my thanks.

Bugs are naturally mine. I'd be glad to hear about them. There are
certainly word - size dependenceies here.

Copyright (c) Matthew Dixon Cowles, <http://www.visi.com/~mdc/>.
Distributable under the terms of the GNU General Public License
version 2. Provided with no warranties of any sort.

Original Version from Matthew Dixon Cowles:
  -> ftp://ftp.visi.com/users/mdc/ping.py

Rewrite by Jens Diemer:
  -> http://www.python-forum.de/post-69122.html#69122

Rewrite by George Notaras:
  -> http://www.g-loaded.eu/2009/10/30/python-ping/

Revision history
~~~~~~~~~~~~~~~~

November 8, 2009
----------------
Improved compatibility with GNU/Linux systems.

Fixes by:
 * George Notaras -- http://www.g-loaded.eu
Reported by:
 * Chris Hallman -- http://cdhallman.blogspot.com

Changes in this release:
 - Re-use time.time() instead of time.clock(). The 2007 implementation
   worked only under Microsoft Windows. Failed on GNU/Linux.
   time.clock() behaves differently under the two OSes[1].

[1] http://docs.python.org/library/time.html#time.clock

May 30, 2007
------------
little rewrite by Jens Diemer:
 -  change socket asterisk import to a normal import
 -  replace time.time() with time.clock()
 -  delete "return None" (or change to "return" only)
 -  in checksum() rename "str" to "source_string"

November 22, 1997
-----------------
Initial hack. Doesn't do much, but rather than try to guess
what features I (or others) will want in the future, I've only
put in what I need now.

December 16, 1997
-----------------
For some reason, the checksum bytes are in the wrong order when
this is run under Solaris 2.X for SPARC but it works right under
Linux x86. Since I don't know just what's wrong, I'll swap the
bytes always and then do an htons().

December 4, 2000
----------------
Changed the struct.pack() calls to pack the checksum and ID as
unsigned. My thanks to Jerome Poincheval for the fix.


Last commit info:
~~~~~~~~~~~~~~~~~
$LastChangedDate: $
$Rev: $
$Author: $
"""

import select
import socket
import struct
import time

# From /usr/include/linux/icmp.h; your milage may vary.
ICMP_ECHO_REQUEST = 8  # Seems to be the same on Solaris.


def checksum(source_bytes):
	# I'm not too confident that this is right but testing seems
	# to suggest that it gives the same answers as in_cksum in ping.c
	sum = 0
	countTo = (len(source_bytes) / 2) * 2
	count = 0
	while count < countTo:
		thisVal = source_bytes[count + 1] * 256 + source_bytes[count]
		sum = sum + thisVal
		sum = sum & 0xFFFFFFFF  # Necessary?
		count = count + 2

	if countTo < len(source_bytes):
		sum = sum + source_bytes[len(source_bytes) - 1]
		sum = sum & 0xFFFFFFFF  # Necessary?

	sum = (sum >> 16) + (sum & 0xFFFF)
	sum = sum + (sum >> 16)
	answer = ~sum
	answer = answer & 0xFFFF

	# Swap bytes. Bugger me if I know why.
	answer = answer >> 8 | (answer << 8 & 0xFF00)

	return answer


def receive_one_ping(my_socket, ID, timeout):
	"""
	receive the ping from the socket.
	"""
	timeLeft = timeout
	while True:
		startedSelect = time.perf_counter()

		whatReady = select.select([my_socket], [], [], timeLeft)
		howLongInSelect = None

		howLongInSelect = time.perf_counter() - startedSelect

		if whatReady[0] == []:  # Timeout
			return

		timeReceived = time.perf_counter()

		recPacket, _ = my_socket.recvfrom(1024)
		icmpHeader = recPacket[20:28]
		# type, code, checksum, packetID, sequence
		_, _, _, packetID, _ = struct.unpack("bbHHh", icmpHeader)
		if packetID == ID:
			bytesInDouble = struct.calcsize("d")
			timeSent = struct.unpack("d", recPacket[28 : 28 + bytesInDouble])[0]
			return timeReceived - timeSent

		timeLeft = timeLeft - howLongInSelect
		if timeLeft <= 0:
			return


def send_one_ping(my_socket, dest_addr, ID):
	"""
	Send one ping to the given >dest_addr<.
	"""
	dest_addr = socket.gethostbyname(dest_addr)

	# Header is type (8), code (8), checksum (16), id (16), sequence (16)
	my_checksum = 0

	# Make a dummy heder with a 0 checksum.
	header = struct.pack("bbHHh", ICMP_ECHO_REQUEST, 0, my_checksum, ID, 1)
	bytesInDouble = struct.calcsize("d")
	data = (192 - bytesInDouble) * b"Q"
	data = struct.pack("d", time.perf_counter()) + data

	# Calculate the checksum on the data and the dummy header.
	my_checksum = checksum(header + data)

	# Now that we have the right checksum, we put that in. It's just easier
	# to make up a new header than to stuff it into the dummy.
	header = struct.pack(
		"bbHHh", ICMP_ECHO_REQUEST, 0, socket.htons(my_checksum), ID, 1
	)
	packet = header + data
	my_socket.sendto(packet, (dest_addr, 1))  # Don't know about the 1


def ping(dest_addr, timeout=2):
	"""
	Returns either the delay (in seconds) or none on timeout.
	"""
	icmp = socket.getprotobyname("icmp")
	try:
		my_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, icmp)
	except (
		OSError
	) as error:  # Exception type changed from socket.error to OSError in python3.3
		if error.errno == 1:
			# Operation not permitted
			msg = " - Note that ICMP messages can only be sent from processes running as root."
			raise OSError(1, msg) from error
		raise  # raise the original error

	my_ID = int(time.time() * 100000) & 0xFFFF

	send_one_ping(my_socket, dest_addr, my_ID)
	delay = receive_one_ping(my_socket, my_ID, timeout)

	my_socket.close()
	return delay


def verbose_ping(dest_addr, timeout=2, count=4):
	"""
	Send >count< ping to >dest_addr< with the given >timeout< and display
	the result.
	"""
	for _ in range(count):
		print("ping %s..." % dest_addr, end=" ")
		try:
			delay = ping(dest_addr, timeout)
		except socket.gaierror as e:
			print("failed. (socket error: '%s')" % e[1])
			break

		if delay is None:
			print("failed. (timeout within %ssec.)" % timeout)
		else:
			delay = delay * 1000
			print("get ping in %0.4fms" % delay)
	print()
