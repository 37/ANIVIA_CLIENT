from audio import ProcessAudio
import time

if __name__ == '__main__':
    ProcessAudio()
    # Keep the program running as listening is now threaded.
    while True: time.sleep(0.1)