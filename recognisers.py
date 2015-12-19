#!/usr/bin/env python3

"""Library for performing speech recognition with support for Google Speech Recognition, Wit.ai, IBM Speech to Text, and AT&T Speech to Text."""

__author__ = "Black.ai"
__version__ = "0.0.1"
__license__ = "BSD"

import io, os, subprocess, wave, base64
import math, audioop, collections, threading
import platform, stat
import json
import urllib.parse

try: # try to use python2 module
	from urllib2 import Request, urlopen, URLError, HTTPError, urlencode, parse
except ImportError: # otherwise, use python3 module
	from urllib.request import Request, urlopen
	from urllib.error import URLError, HTTPError

# define exceptions
class WaitTimeoutError(Exception): pass
class RequestError(Exception): pass
class UnknownValueError(Exception): pass

class AudioSource(object):
	def __init__(self):
		raise NotImplementedError("this is an abstract class")

	def __enter__(self):
		raise NotImplementedError("this is an abstract class")

	def __exit__(self, exc_type, exc_value, traceback):
		raise NotImplementedError("this is an abstract class")

try:
	import pyaudio
	class Microphone(AudioSource):
		"""
		This is available if PyAudio is available, and is undefined otherwise.

		Creates a new ``Microphone`` instance, which represents a physical microphone on the computer. Subclass of ``AudioSource``.

		If ``device_index`` is unspecified or ``None``, the default microphone is used as the audio source. Otherwise, ``device_index`` should be the index of the device to use for audio input.

		A device index is an integer between 0 and ``pyaudio.get_device_count() - 1`` (assume we have used ``import pyaudio`` beforehand) inclusive. It represents an audio device such as a microphone or speaker. See the `PyAudio documentation <http://people.csail.mit.edu/hubert/pyaudio/docs/>`__ for more details.

		The microphone audio is recorded in chunks of ``chunk_size`` samples, at a rate of ``sample_rate`` samples per second (Hertz).

		Higher ``sample_rate`` values result in better audio quality, but also more bandwidth (and therefore, slower recognition). Additionally, some machines, such as some Raspberry Pi models, can't keep up if this value is too high.

		Higher ``chunk_size`` values help avoid triggering on rapidly changing ambient noise, but also makes detection less sensitive. This value, generally, should be left at its default.
		"""
		def __init__(self, device_index = None, sample_rate = 16000, chunk_size = 1024):
			assert device_index is None or isinstance(device_index, int), "Device index must be None or an integer"
			if device_index is not None: # ensure device index is in range
				audio = pyaudio.PyAudio(); count = audio.get_device_count(); audio.terminate() # obtain device count
				assert 0 <= device_index < count, "Device index out of range"
			assert isinstance(sample_rate, int) and sample_rate > 0, "Sample rate must be a positive integer"
			assert isinstance(chunk_size, int) and chunk_size > 0, "Chunk size must be a positive integer"
			self.device_index = device_index
			self.format = pyaudio.paInt16 # 16-bit int sampling
			self.SAMPLE_WIDTH = pyaudio.get_sample_size(self.format) # size of each sample
			self.SAMPLE_RATE = sample_rate # sampling rate in Hertz
			self.CHUNK = chunk_size # number of frames stored in each buffer

			self.audio = None
			self.stream = None

		def __enter__(self):
			assert self.stream is None, "This audio source is already inside a context manager"
			self.audio = pyaudio.PyAudio()
			self.stream = self.audio.open(
				input_device_index = self.device_index, channels = 1,
				format = self.format, rate = self.SAMPLE_RATE, frames_per_buffer = self.CHUNK,
				input = True, # stream is an input stream
			)
			return self

		def __exit__(self, exc_type, exc_value, traceback):
			if not self.stream.is_stopped():
				self.stream.stop_stream()
			self.stream.close()
			self.stream = None
			self.audio.terminate()
except ImportError:
	pass

class AudioData(object):
	def __init__(self, frame_data, sample_rate, sample_width):
		assert sample_rate > 0, "Sample rate must be a positive integer"
		assert sample_width % 1 == 0 and sample_width > 0, "Sample width must be a positive integer"
		self.frame_data = frame_data
		self.sample_rate = sample_rate
		self.sample_width = int(sample_width)

class Recognizer(AudioSource):
	def __init__(self):
		"""
		Creates a new ``Recognizer`` instance, which represents a collection of speech recognition functionality.
		"""
		self.energy_threshold = 600 # minimum audio energy to consider for recording
		self.dynamic_energy_threshold = False # Allows the microphone sensitivity to dynamically change
		self.dynamic_energy_adjustment_damping = 0.15
		self.dynamic_energy_ratio = 2.0
		self.pause_threshold = 0.5 # seconds of non-speaking audio before a phrase is considered complete
		self.phrase_threshold = 0.5 # minimum seconds of speaking audio before we consider the speaking audio a phrase - values below this are ignored (for filtering out clicks and pops)
		self.non_speaking_duration = 0.2 # seconds of non-speaking audio to keep on both sides of the recording

	def record(self, source, duration = None, offset = None):
		"""
		Records up to ``duration`` seconds of audio from ``source`` (an ``AudioSource`` instance) starting at ``offset`` (or at the beginning if not specified) into an ``AudioData`` instance, which it returns.

		If ``duration`` is not specified, then it will record until there is no more audio input.
		"""
		assert isinstance(source, AudioSource), "Source must be an audio source"

		frames = io.BytesIO()
		seconds_per_buffer = (source.CHUNK + 0.0) / source.SAMPLE_RATE
		elapsed_time = 0
		offset_time = 0
		offset_reached = False
		while True: # loop for the total number of chunks needed
			if offset and not offset_reached:
				offset_time += seconds_per_buffer
				if offset_time > offset:
					offset_reached = True

			buffer = source.stream.read(source.CHUNK)
			if len(buffer) == 0: break

			if offset_reached or not offset:
				elapsed_time += seconds_per_buffer
				if duration and elapsed_time > duration: break

				frames.write(buffer)

		frame_data = frames.getvalue()
		frames.close()
		return AudioData(frame_data, source.SAMPLE_RATE, source.SAMPLE_WIDTH)

	def adjust_for_ambient_noise(self, source, duration = 1):
		"""
		Adjusts the energy threshold dynamically using audio from ``source`` (an ``AudioSource`` instance) to account for ambient noise.

		Intended to calibrate the energy threshold with the ambient energy level. Should be used on periods of audio without speech - will stop early if any speech is detected.

		The ``duration`` parameter is the maximum number of seconds that it will dynamically adjust the threshold for before returning. This value should be at least 0.5 in order to get a representative sample of the ambient noise.
		"""
		assert isinstance(source, AudioSource), "Source must be an audio source"
		assert self.pause_threshold >= self.non_speaking_duration >= 0

		seconds_per_buffer = (source.CHUNK + 0.0) / source.SAMPLE_RATE
		elapsed_time = 0

		# adjust energy threshold until a phrase starts
		while True:
			elapsed_time += seconds_per_buffer
			if elapsed_time > duration: break
			buffer = source.stream.read(source.CHUNK)
			energy = audioop.rms(buffer, source.SAMPLE_WIDTH) # energy of the audio signal

			# dynamically adjust the energy threshold using assymmetric weighted average
			damping = self.dynamic_energy_adjustment_damping ** seconds_per_buffer # account for different chunk sizes and rates
			target_energy = energy * self.dynamic_energy_ratio
			self.energy_threshold = self.energy_threshold * damping + target_energy * (1 - damping)

	def listen(self, source, timeout = None):
		"""
		Records a single phrase from ``source`` (an ``AudioSource`` instance) into an ``AudioData`` instance, which it returns.

		This is done by waiting until the audio has an energy above ``recognizer_instance.energy_threshold`` (the user has started speaking), and then recording until it encounters ``recognizer_instance.pause_threshold`` seconds of non-speaking or there is no more audio input. The ending silence is not included.

		The ``timeout`` parameter is the maximum number of seconds that it will wait for a phrase to start before giving up and throwing an ``speech_recognition.WaitTimeoutError`` exception. If ``timeout`` is ``None``, it will wait indefinitely.
		"""
		assert isinstance(source, AudioSource), "Source must be an audio source"
		assert self.pause_threshold >= self.non_speaking_duration >= 0

		seconds_per_buffer = (source.CHUNK + 0.0) / source.SAMPLE_RATE
		pause_buffer_count = int(math.ceil(self.pause_threshold / seconds_per_buffer)) # number of buffers of non-speaking audio before the phrase is complete
		phrase_buffer_count = int(math.ceil(self.phrase_threshold / seconds_per_buffer)) # minimum number of buffers of speaking audio before we consider the speaking audio a phrase
		non_speaking_buffer_count = int(math.ceil(self.non_speaking_duration / seconds_per_buffer)) # maximum number of buffers of non-speaking audio to retain before and after

		# read audio input for phrases until there is a phrase that is long enough
		elapsed_time = 0 # number of seconds of audio read
		while True:
			frames = collections.deque()

			# store audio input until the phrase starts
			while True:
				elapsed_time += seconds_per_buffer
				if timeout and elapsed_time > timeout: # handle timeout if specified
					raise WaitTimeoutError("listening timed out")

				buffer = source.stream.read(source.CHUNK)
				if len(buffer) == 0: break # reached end of the stream
				frames.append(buffer)
				if len(frames) > non_speaking_buffer_count: # ensure we only keep the needed amount of non-speaking buffers
					frames.popleft()

				# detect whether speaking has started on audio input
				energy = audioop.rms(buffer, source.SAMPLE_WIDTH) # energy of the audio signal
				if energy > self.energy_threshold: break

				# dynamically adjust the energy threshold using assymmetric weighted average
				if self.dynamic_energy_threshold:
					damping = self.dynamic_energy_adjustment_damping ** seconds_per_buffer # account for different chunk sizes and rates
					target_energy = energy * self.dynamic_energy_ratio
					self.energy_threshold = self.energy_threshold * damping + target_energy * (1 - damping)

			# read audio input until the phrase ends
			pause_count, phrase_count = 0, 0
			while True:
				elapsed_time += seconds_per_buffer

				buffer = source.stream.read(source.CHUNK)
				if len(buffer) == 0: break # reached end of the stream
				frames.append(buffer)
				phrase_count += 1

				# check if speaking has stopped for longer than the pause threshold on the audio input
				energy = audioop.rms(buffer, source.SAMPLE_WIDTH) # energy of the audio signal
				if energy > self.energy_threshold:
					pause_count = 0
				else:
					pause_count += 1
				if pause_count > pause_buffer_count: # end of the phrase
					break

			# check how long the detected phrase is, and retry listening if the phrase is too short
			phrase_count -= pause_count
			if phrase_count >= phrase_buffer_count: break # phrase is long enough, stop listening

		# obtain frame data
		for i in range(pause_count - non_speaking_buffer_count): frames.pop() # remove extra non-speaking frames at the end
		frame_data = b"".join(list(frames))

		return AudioData(frame_data, source.SAMPLE_RATE, source.SAMPLE_WIDTH)

	def listen_in_background(self, source, callback):
		"""
		Spawns a thread to repeatedly record phrases from ``source`` (an ``AudioSource`` instance) into an ``AudioData`` instance and call ``callback`` with that ``AudioData`` instance as soon as each phrase are detected.

		Returns a function object that, when called, requests that the background listener thread stop, and waits until it does before returning. The background thread is a daemon and will not stop the program from exiting if there are no other non-daemon threads.

		Phrase recognition uses the exact same mechanism as ``recognizer_instance.listen(source)``.

		The ``callback`` parameter is a function that should accept two parameters - the ``recognizer_instance``, and an ``AudioData`` instance representing the captured audio. Note that ``callback`` function will be called from a non-main thread.
		"""
		assert isinstance(source, AudioSource), "Source must be an audio source"
		running = [True]
		def threaded_listen():
			with source as s:
				while running[0]:
					try: # listen for 1 second, then check again if the stop function has been called
						audio = self.listen(s, 1)
					except WaitTimeoutError: # listening timed out, just try again
						pass
					else:
						if running[0]: callback(audio)
		def stopper():
			running[0] = False
			listener_thread.join() # block until the background thread is done
		listener_thread = threading.Thread(target=threaded_listen)
		listener_thread.daemon = True
		listener_thread.start()
		return stopper


def shutil_which(pgm):
	"""
	python2 backport of python3's shutil.which()
	"""
	path = os.getenv('PATH')
	for p in path.split(os.path.pathsep):
		p = os.path.join(p, pgm)
		if os.path.exists(p) and os.access(p, os.X_OK):
			return p