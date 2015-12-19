#!/usr/bin/env python3

import speech_recognition as sr

from os import path
WAV_FILE = path.join(path.dirname(path.realpath(__file__)), "test.wav")

# use "test.wav" as the audio source
r = sr.Recognizer()
with sr.WavFile("test.wav") as source:
    audio = r.record(source) # read the entire WAV file

# recognize speech using Google Speech Recognition
try:
    # for testing purposes, we're just using the default API key
    # to use another API key, use `r.recognize_google(audio, key="GOOGLE_SPEECH_RECOGNITION_API_KEY")`
    # instead of `r.recognize_google(audio)`
    print("Google Speech Recognition thinks you said " + r.recognize_google(audio))
except LookupError:
    print("Google Speech Recognition could not understand audio")
