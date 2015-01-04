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
import sys, time, math
import errno, audioop
import struct

# External phonepatch modules
import soundcard

__version__ = "$Revision: 1.12 $"
__author__ = "Arnau Sanchez <arnau@ehas.org>"
__depends__ = ['Python-2.4']
__copyright__ = """Copyright (C) 2006 Arnau Sanchez <arnau@ehas.org>.
This code is distributed under the terms of the GNU General Public License."""

##############################
###############################
class Radio:
	"""Use soundcard and external PTT apps to interface with a radio transceiver.
	
	Thie class provices a simple and easy way to send and receive audio voice 
	(even data) with standard transceivers, using soundcard as D/A and D/A 
	converter. Moreover, it allows controlling the PTT (Push-to-Talk) line which
	toggle between the reception (Rx) or transmition (Tx) state. 
	"""

	###############################
	def __init__(self, soundcard_device, samplerate, ptt, carrier, verbose=False, \
		soundcard_retries=1, fullduplex=False, latency=None, ctcss_mintime=False):
		"""Open a soundcard and PTT interface.
		Use radio_control object to set PTT and get carrier-detection state.
		
		Soundcard device should be OSS files (/dev/dspX). Parameter 
		<samplerate> will be the rate used by soundcard.
		
		PTT object is an instance  of ExecInterface with "on" and "off"
		commands defined.
		"""
		self.samplerate = samplerate
		self.verbose = verbose
		self.ptt = ptt
		self.carrier = carrier
		
		# Carrier parameters
		self.fullduplex = fullduplex
		
		# Soundcard parameters
		self.sampleformat = "S16_LE"
		self.audio_channels = 1
		self.buffer_size = 1024
		self.sample_width = 2
		self.sample_max = 2.0**(self.sample_width*8) / 2.0
		
		# Latency (allowe dbetween 0.01 and secs) gives the fragment size 
		self.fragmentsize = None
		if latency:
			self.fragmentsize = (samplerate * self.audio_channels * self.sample_width) * latency
			if self.fragmentsize < 128: self.fragmentsize = 128
			elif self.fragmentsize > 32768: self.fragmentsize = 32768
			self.fragmentsize = 2**int(math.log(self.fragmentsize, 2))
			self.debug("soundcard fragment size: %d bytes" %self.fragmentsize)
			
		self.onoff_dict = {False: "off", True: "on"}
		self.ptt_offtime = self.ptt_ontime = self.ptt_tailtime = 0
		self.carrier_offtime = self.carrier_ontime = self.carrier_tailtime = 0
		self.carrier_state = None
		self.set_carrier_state(False)
	
		# CTCSS generator/decoder		
		if ctcss_mintime:
			import ctcss
			self.ctcss_generator = ctcss.Generator(self.samplerate, self.sample_width)
			self.ctcss_decoder = ctcss.Decoder(self.samplerate, self.sample_width, ctcss_mintime)
		else: self.ctcss_generator = self.ctcss_decoder = None
		
		# Open soundcard
		self.soundcard = None
		self.soundcard_device = soundcard_device
		while 1:
			try: self.soundcard = self.open_soundcard(device = soundcard_device, \
					channels = self.audio_channels, mode = "rw", library = "oss", \
					samplerate = samplerate, sampleformat = self.sampleformat, \
					fragmentsize = self.fragmentsize)
			except IOError, (nerror, detail): 
				if nerror != errno.EBUSY: break
				soundcard_retries -= 1
				if not soundcard_retries: break
				self.debug("soundcard busy, remaining retries: %d" %soundcard_retries)
				time.sleep(1)
			else: break
				
		if not self.soundcard:		
			raise IOError, "cannot open soundcard: %s" %soundcard_device
			
		# Turn PTT off at start (for safety)
		self.set_ptt(False)
		
	###################################
	def open_soundcard(self, *args, **kwargs):
		self.open_soundcard_args = args, kwargs
		return soundcard.Soundcard(*args, **kwargs)

	###################################
	def reopen_soundcard(self):
		self.soundcard.close()
		args, kwargs = self.open_soundcard_args
		self.soundcard = soundcard.Soundcard(*args, **kwargs)

	###################################
	def debug(self, args, exit = False):
		"""Write logs to standard error if enabled"""
		if not self.verbose: return
		log = "radio -- "
		if exit: log += "fatal error - "
		log += str(args) + "\n"
		sys.stderr.write(log)
		sys.stderr.flush()
		if exit: sys.exit(1)
		
	###################################
	def get_audiofd(self):
		"""Get audio file descriptor used to interface soundcard"""
		return self.soundcard

	###################################
	def get_fragmentsize(self):
		"""Get audio file descriptor used to interface soundcard"""
		return self.fragmentsize

	#####################################
	def limit_power(self, buffer, limit):
		power = float(audioop.rms(buffer, self.sample_width)) / self.sample_max
		if power > limit:
			return audioop.mul(buffer, self.sample_width, limit/power)
		else: return buffer
		
	#####################################
	def read_audio(self, size, power_limit=1.0):
		"""Read data from soundcard""" 
		if not self.soundcard: self.debug("soundcard not opened"); return
		buffer = self.soundcard.read(size)
		if not buffer: return
		buffer = self.update_carrier_state(buffer)
		if power_limit < 1.0:
			buffer = self.limit_power(buffer, power_limit)
		return buffer

	#####################################
	def decode_ctcss(self, buffer):
		if not self.ctcss_decoder or not self.carrier_state: return
		self.ctcss_decoder.decode_buffer(buffer)

	#####################################
	def clear_ctcss(self):
		if not self.ctcss_decoder: return
		self.ctcss_decoder.clear_tone()
		
	#####################################
	def get_ctcss_tone(self):
		#return 200.0
		if not self.ctcss_decoder: return
		return self.ctcss_decoder.get_tone()
		
	#####################################
	def update_carrier_state(self, buffer):
		"""Update carrier_detection state"""
		if not self.carrier: return buffer
		if self.carrier.type == "audio": return buffer
		try: next_time = self.time_next_carrier
		except: next_time = 0
		now = time.time()
		if now > next_time:
			try: self.set_carrier_state(self.carrier.get())
			except: self.debug("cannot get carrier state"); return buffer
			self.time_next_carrier = now + self.carrier.pollingtime			
		# Return a void buffer if there is no carrier detection
		if self.carrier and self.carrier.type == "on" and not self.carrier_state:
			return "\x00" * len(buffer)
		return buffer
			
	########################################
	def set_carrier_state(self, state):
		if self.carrier_state != state:
			self.debug("new carrier state: %s" %self.onoff_dict[state])
			self.carrier_state = state
		
	########################################
	def is_ptt_blocked(self):
		"""Return a bool indicating if is possible to set the ptt on, 
		otherwise the carrier detection is blocking it"""
		if not self.carrier or self.fullduplex or not self.carrier_state:
			return False
		return True
		
	#####################################
	def vox_toradio(self, buffer, ctcss=None):
		"""VOX PTT processing.
		
		Set PTT on if audio data in buffer reaches the threshold. 
		Control minimum and maximum PTT on/off states.
		"""
		if not self.soundcard: raise IOError, "Soundcard not opened"
		
		if not self.ptt: 
			self.send_audio(buffer, ctcss)
			return
		
		# Get power of audio fragment for VOX
		power = audioop.rms(buffer, self.sample_width) / self.sample_max
		now = time.time()
		
		if power >= self.ptt.threshold and now >= self.ptt_ontime:
			self.ptt_tailtime = now + self.ptt.tailtime
			if not self.ptt.get():
				self.debug("input power threshold reached: %0.4f" %self.ptt.threshold)
				# Thereshold for PTT reached, but check before if not carrier is detected
				if not self.is_ptt_blocked():
					self.set_ptt(True)
					self.ptt_ontime = 0
					if self.ptt.maxtime:
						self.ptt_offtime = now + self.ptt.maxtime
				else: self.debug("PTT blocked due to carrier detection")
			elif self.ptt_offtime and now >= self.ptt_offtime and not self.ptt_ontime:
				self.debug("ptt_max_time timed out: turn PTT off and wait %d seconds" %self.ptt.waittime)
				self.set_ptt(False)
				self.ptt_ontime = now + self.ptt.waittime
			elif self.is_ptt_blocked():
				self.debug("PTT blocked turned off due to carrier detection")
				self.set_ptt(False)
				
		elif self.ptt.get():
			if now >= self.ptt_tailtime:
				self.debug("ptt_tail_time reached")
				self.set_ptt(False)
			elif self.is_ptt_blocked():
				self.debug("PTT blocked due to carrier detection")
				self.set_ptt(False)

		#if self.ptt.get():
		self.send_audio(buffer, ctcss)

	#####################################
	def vox_topeer(self, peerfd, buffer):
		"""VOX PTT processing.
		
		Set PTT on if audio data in buffer reaches the threshold. 
		Control minimum and maximum PTT on/off states.
		"""
		if not self.carrier or self.carrier.type != "audio": 
			peerfd.write(buffer)
			peerfd.flush()
			return
		
		# Get power of audio fragment for VOX
		power = audioop.rms(buffer, self.sample_width) / self.sample_max
		now = time.time()
		
		if power >= self.carrier.threshold and now >= self.carrier_ontime:
			self.carrier_tailtime = now + self.carrier.tailtime
			if not self.carrier_state:
				self.debug("input power threshold for radio reached: %0.4f" %self.carrier.threshold)
				if self.ptt.get(): self.set_ptt(False)
				self.carrier_ontime = 0
				if self.carrier.maxtime: 
					self.carrier_offtime = now + self.carrier.maxtime
				self.set_carrier_state(True)
			elif self.carrier_offtime and now >= self.carrier_offtime and not self.carrier_ontime:
				self.debug("carrier_max_time timed out: disabling carrier_detection for %d seconds" %self.ptt.waittime)
				self.set_carrier_state(False)
				self.carrier_ontime = now + self.carrier.waittime
				
		elif self.carrier_state and now >= self.carrier_tailtime:
			self.debug("carrier_tail_time reached")
			self.set_carrier_state(False)

		#if self.ptt.get():
		peerfd.write(buffer)
		peerfd.flush()
			

	#####################################
	def send_audio(self, buffer, ctcss=None):
		"""Send audio to radio transceiver using the soundcard
		
		ctcss -- Tuple containing (frequecy, amplitude) for CTCSS code generation
		"""
		if not self.soundcard: self.debug("soundcard not opened"); return
		if not buffer: return
				
		if ctcss and self.ctcss_generator:
			freq, amplitude = ctcss
			ctcss_buffer = self.ctcss_generator.generate(len(buffer), amplitude, freq)
			buffer = audioop.add(buffer, ctcss_buffer, self.sample_width)

		self.soundcard.write(buffer)

	#####################################
	def flush_audio(self):
		"""Flush buffer soundcard"""
		self.soundcard.sync()

	###################################
	def close(self):
		"""Close radio interface"""
		self.debug("closing radio interface")
		
		if self.soundcard: 
			self.soundcard.close()
			self.soundcard = None
			self.debug("soundcard closed")
		else: self.debug("soundcard was not opened")
		
		self.set_ptt(False)

	###################################
	def set_ptt(self, value):
		if not self.ptt: return
		self.debug("set PTT: %s" %self.onoff_dict[bool(value)])
		self.ptt.set(value)