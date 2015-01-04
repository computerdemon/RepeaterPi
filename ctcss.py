#!/usr/bin/python

# This file is part of asterisk-phonepatch

# Copyright (C) 2006 Arnau Sanchez
#
# Asterisk-phonepatch is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License or any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

# Standard Python modules
import struct, math
import numarray, FFT

__version__ = "$Revision: 1.5 $"
__author__ = "Arnau Sanchez <arnau@ehas.org>"
__depends__ = ['OSSAudioDev', 'FFT', 'Numeric-Extension', 'Python-2.4']
__copyright__ = """Copyright (C) 2006 Arnau Sanchez <arnau@ehas.org>.
This code is distributed under the terms of the GNU General Public License."""

CTCSS_FREQS =[67.0, 69.3, 71.9, 74.4, 77.0, 79.7, 82.5, 85.4, 88.5, 91.5, 94.8, 97.4, 100.0,
        103.5,  107.2, 110.9, 114.8, 118.8, 123.0, 127.3, 131.8, 136.5, 141.3, 146.2, 151.4, 
        156.7, 162.2, 167.9, 173.8, 179.9, 186.2, 192.8, 203.5, 206.5,  210.7, 218.1, 225.7, 
        229.2, 233.6, 241.8, 250.3, 254.1]

#########################
class Generator:
	#########################
	def __init__(self, samplerate, samplewidth):
		self.samplerate = samplerate
		self.samplewidth = samplewidth
		self.sinindex = 0
		self.samplemax = 2.0**(8*samplewidth) / 2.0

	#########################
	def generate(self, length, amplitude, freq):
		start = self.sinindex
		nbuffer = length
		anbuffer = nbuffer / self.samplewidth
		ctcss_signal = [self.samplemax*amplitude*math.sin(2*math.pi*freq*x/self.samplerate) \
			for x in range(start, start+anbuffer)]
		self.sinindex += anbuffer
		format = "<%dh" %anbuffer
		return struct.pack(format, *ctcss_signal)

#########################
class Decoder:
	MINPOWER = 0.001
	OVERPOWER = 5
	UPFACTOR = 1
	DOWNFACTOR = 0.5
	MEANFREQSUSED = 20

	MINSAMPLERATE = 8000
	SUBWINDOW = 4
	SAMPLEFORMAT = {1: "b", 2: "h"}
	
	#########################
	def __init__(self, samplerate=8000, samplewidth=2, mintime=0.5):
		if samplerate < self.MINSAMPLERATE: 
			raise ValueError, "Samplerate must be %d sps or more: %s" %(self.MINSAMPLERATE, samplerate)
		if samplewidth not in self.SAMPLEFORMAT:
			raise ValueError, "Invalid sample width: %s" %samplewidth
		if mintime < 0.1: mintime = 0.1
		self.samplerate = samplerate
		self.samplewidth = samplewidth
		self.detect_tones = CTCSS_FREQS

		self.threshold = self.SUBWINDOW
		self.windowsize = int((float(samplerate)*mintime) / self.threshold)
		self.samplemax = 2.0**(8*samplewidth) / 2.0
		self.buffer = ""
		self.tone_detected = self.tone_current = None
		self.ntone = 0
		self.upfactor = self.UPFACTOR
		self.downfactor = self.DOWNFACTOR
		self.cosarray = {}
		self.sinarray = {}
		for freq in self.detect_tones:
			k = 2*math.pi*freq/self.samplerate
			self.sinarray[freq] = numarray.array([math.sin(k*x) for x in xrange(self.windowsize)])
			self.cosarray[freq] = numarray.array([math.cos(k*x) for x in xrange(self.windowsize)])

	#########################
	def get_tone(self):
		return self.tone_detected

	#########################
	def clear_tone(self):
		self.tone_detected = self.tone_current = None

	#########################
	def decode_buffer(self, buffer):
		self.buffer += buffer
		length = self.samplewidth * self.windowsize
		format = self.SAMPLEFORMAT[self.samplewidth]
		while len(self.buffer) >= length: 
			buffer = self.buffer[:length]
			self.buffer = self.buffer[length:]			
			window = numarray.array(struct.unpack("%d%s" %(len(buffer)/self.samplewidth, format), buffer))
			out = []
			for freq in self.detect_tones:
				value = ((((self.sinarray[freq] * window)).sum())**2 + (((self.cosarray[freq] * window)).sum())**2)
				out.append((value, freq))
			out.sort()
			out.reverse()
			maxpower, freq = out[0]
			
			meanused = self.MEANFREQSUSED
			meanpower = 0
			for value in [x[0] for x in out[-meanused:]]:
				meanpower += value
			meanpower = math.sqrt(meanpower/meanused) / (self.windowsize * self.samplemax)
			maxpower = math.sqrt(maxpower) / (self.windowsize * self.samplemax)
			if meanpower < 0.0000000001:
				overpower = 10*self.OVERPOWER
			else: overpower = maxpower / meanpower
			
			#print "debug: %f, %f, %f, %f, %d, %d" %(maxpower, meanpower, overpower, freq, self.windowsize, self.threshold)
			mindiff = CTCSS_FREQS[-1]
			for f in self.detect_tones:
				diff = abs(freq - f)
				if diff < mindiff:
					mindiff = diff
					ctcssfreq = f
				else: break
			if maxpower > self.MINPOWER and overpower > self.OVERPOWER and self.tone_current == ctcssfreq:
				self.ntone += self.upfactor
				if self.ntone >= self.threshold:
					self.ntone = self.threshold
					self.tone_detected = ctcssfreq
			else:
				self.ntone -= self.downfactor
				if self.ntone < 0:
					self.tone_current = ctcssfreq
					self.ntone = self.upfactor
					self.tone_detected = None


###########################
def main():
	import os, sys, optparse
	usage = """
	ctcss.py [options]: CTCSS Generator/Decoder
	
	You must activate a generate or decoding option"""
	
	parser = optparse.OptionParser(usage)
	
	parser.add_option('-s', '--samplerate', dest='samplerate', default = 8000, metavar='SPS', type='int', help = 'Set sampling rate')
	parser.add_option('-w', '--samplewidth', dest='samplewidth', default = 2, metavar='BYTES', type='int', help = 'Set sample width')
	parser.add_option('-b', '--buffersize', dest='buffersize', default = 1024, metavar = "BYTES", type = 'int', help = 'Buffer size for input/output')
	parser.add_option('-g', '--generate', dest='generate', default = "", metavar='TIME,AMPLITUDE,FREQ', type='string', help = 'CTCSS generator')
	parser.add_option('-d', '--decode', dest='decode', default = False, action='store_true', help = 'CTCSS decoder')
	parser.add_option('-m', '--mintime', dest='mintime', default = 0.5, metavar = "SECONDS", type = 'float', help = 'Threshold detection time')

	options, args = parser.parse_args()
	
	if options.decode:
		dec = Decoder(options.samplerate, options.samplewidth, options.mintime)
		oldtone = None
		while 1:
			buffer = os.read(0, options.buffersize)
			if not buffer: break
			dec.decode_buffer(buffer)
			tone = dec.get_tone()
			if tone != oldtone: 
				sys.stdout.write(str(tone) + "\n")
				sys.stdout.flush()
				oldtone = tone	
	elif options.generate:
		try: time, amplitude, freq = [float(x.strip()) for x in options.generate.split(",")]
		except: sys.stderr.write("Syntax error on generate options: %s\n" %options.generate); parser.print_help(); sys.exit(1)
		gen = Generator(options.samplerate, options.samplewidth)
		total = int(options.samplerate * options.samplewidth * time)
		nbuffer = options.buffersize
		while total > 0:
			buffer = gen.generate(min(total, nbuffer), amplitude, freq)
			sys.stdout.write(buffer)
			total -= nbuffer
	else:
		sys.stderr.write("Need --generate or --decode options\n")
		parser.print_help()
		sys.exit(1)
	sys.exit(0)

#########
############
if __name__ == "__main__":
	main()