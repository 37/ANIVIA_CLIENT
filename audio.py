# Black.ai technologies 2015
#!/usr/bin/env python3
# See documentation for speech_recognition at: https://pypi.python.org/pypi/SpeechRecognition/
# NOTE: this example requires PyAudio because it uses the Microphone class

import json
import recognisers as sr
from action import Ani


class ProcessAudio():
	def __init__(self):

		# obtain audio from the microphone
		self.r = sr.Recognizer()
		mic = sr.Microphone()

		# Start listener
		try:
			print("A moment of silence, please...")
			with mic as source:
				self.r.adjust_for_ambient_noise(source)
				print("Set minimum energy threshold to {}".format(self.r.energy_threshold))
				print("Microphone ready, Speak away!")

		except KeyboardInterrupt:
			pass

		# Initialises listener
		self.r.listen_in_background(mic, self.processAudio)


	def processAudio(self, audio):

		print("\033[95mGot it! Now to recognize it...")
		Ani.recognition(audio)
