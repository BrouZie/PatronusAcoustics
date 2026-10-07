"""Continuously stream a WAV file as mono Q31 over UART, paced like a live mic."""
import argparse
import time

import librosa
import numpy as np
import serial


def load_wav(path, target_rate):
    y, _ = librosa.load(path, sr=target_rate, mono=True)   # (n,) float32 in [-1, 1]
    q31 = np.clip(np.round(y * 2147483648.0), -2147483648, 2147483647).astype("<i4")
    q31 &= np.int32(-256)       # ICS-52000 is 24-bit, low 8 bits are 0
    return q31.tobytes()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("wav")
    p.add_argument("--port", required=True, help="e.g. COM5 or /dev/ttyACM0")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--hop", type=int, default=512,
                   help="samples per chunk (ICS_HOP_SAMPLES); chunk is hop*4 bytes")
    p.add_argument("--rate", type=int, default=16000,
                   help="target sample rate (match AUDIO_SAMPLE_RATE_HZ)")
    p.add_argument("--once", action="store_true", help="send the file once instead of looping")
    p.add_argument("--fast", action="store_true", help="no pacing, send as fast as the link allows")
    args = p.parse_args()

    data = load_wav(args.wav, args.rate)
    chunk_bytes = args.hop * 4
    n_chunks = len(data) // chunk_bytes
    if n_chunks == 0:
        raise SystemExit("File shorter than one hop")
    data = data[:n_chunks * chunk_bytes]       # keep the loop hop-aligned
    chunk_period = args.hop / args.rate

    needed = args.rate * 4 * 10                # 8N1 = 10 bits per byte
    print(f"{args.rate} Hz, {n_chunks} chunks of {chunk_bytes} bytes "
          f"({n_chunks * chunk_period:.2f} s per pass)")
    if needed > args.baud:
        print(f"WARNING: need ~{needed} baud for real-time, link is {args.baud}")

    with serial.Serial(args.port, args.baud, timeout=1) as ser:
        ser.reset_output_buffer()
        t0 = time.perf_counter()
        sent = 0                               # chunks sent in total, across all passes
        passes = 0
        try:
            while True:
                for i in range(n_chunks):
                    ser.write(data[i * chunk_bytes:(i + 1) * chunk_bytes])
                    sent += 1
                    if not args.fast:
                        delay = t0 + sent * chunk_period - time.perf_counter()
                        if delay > 0:
                            time.sleep(delay)
                passes += 1
                print(f"pass {passes} done")
                if args.once:
                    break
        except KeyboardInterrupt:
            print("\nStopped")


if __name__ == "__main__":
    main()
