#!/usr/bin/env python3

import speech_recognition as sr

# use "test.wav" as the audio source
r = sr.Recognizer()
with sr.WavFile("test.wav") as source:
    audio = r.record(source) # read the entire WAV file

# recognize speech using Google Speech Recognition
try:
    # for testing purposes, we're just using the default API key
    # to use another API key, use `r.recognize_google(audio, key="GOOGLE_SPEECH_RECOGNITION_API_KEY", show_all=True)`
    # instead of `r.recognize_google(audio, show_all=True)`
    result_list = r.recognize_google(audio, show_all=True)
    print("Google Speech Recognition possible transcriptions:")
    for prediction in result_list:
        print(" {0} ({1}% confidence)".format(prediction["text"], prediction["confidence"] * 100))
except LookupError:
    print("Google Speech Recognition could not understand audio")

# recognize speech using Wit.ai
WIT_AI_KEY = "INSERT WIT.AI API KEY HERE" # Wit.ai keys are 32-character uppercase alphanumeric strings
try:
    from pprint import pprint
    print("Wit.ai recognition results:")
    pprint(r.recognize_wit(audio, key=WIT_AI_KEY, show_all=True)) # pretty-print the recognition result
except LookupError:
    print("Wit.ai could not understand audio")
