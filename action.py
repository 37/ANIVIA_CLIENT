###
#Copyright (c) Black ai
###
from pprint import pprint

try:
	from urllib2 import Request, urlopen, URLError, HTTPError, urlencode, parse
except ImportError: # otherwise, use python3 module
	from urllib.request import Request, urlopen
	from urllib.error import URLError, HTTPError
	import urllib.parse


class Ani():

	def recognition(audio):
		# received audio data, now we'll recognize it using Google Speech Recognition
		req_data = audio.frame_data

		# req_host = "http://anivia.au-syd.mybluemix.net"
		req_host = "http://localhost:5000"
		req_headers = {"Content-Type": "application/json"}
		req_params = urllib.parse.urlencode({'token': 'sometoken',
								'samplerate': audio.sample_rate,
								'samplewidth': audio.sample_width,
								'clientid': '1337'})
		req_path = "/api/audible?%s"  % req_params

		# Construct request
		request = Request(req_host + req_path, data = req_data, headers = req_headers)

		try:
			response = urlopen(request)
		except HTTPError as e:
			print("Session request failed: {0}".format(getattr(e, "reason", "status {0}".format(e.code)))) # use getattr to be compatible with Python 2.6
		except URLError as e:
			print("recognition connection failed: {0}".format(getattr(e, "reason", "status {0}".format(e.code)))) # use getattr to be compatible with Python 2.6

		try:
			response_text = response.read().decode("utf-8")
			results = json.loads(response_text)

			if len(results) < 3:
				print ("Error : Strange result")
			else:
				if results["result"]:
					print('\033[92mYou said: ' + results["result"])
				if results["response"]:
					Voice().default(results["response"])
				if results["intent"]:
					Action().default(results["intent"])
		except NameError:
			print('Speak when ready.')


class Action():
	def default(intent):
		print("Intent: ")
		for item in intent:
			print("\033[94m")
			pprint(intent)
		return True


class Voice():
	def default(phrase):
		assert isinstance(phrase, str), "`phrase` must be a string"
		print("\033[93mAni says: " + phrase)
