#pragma once

#include <Arduino.h>
#include <AudioStream.h>

// N-channel audio-graph sink: collects synchronized blocks from up to 16
// inputs into per-channel int16 ring buffers, and hands out overlapping
// analysis frames (frame_size samples, advancing by hop) as float.
//
// update() runs in the audio ISR; frameReady()/readFrame()/consumeFrame()
// are called from loop(). If loop() falls behind, whole frames are dropped
// and counted (overruns()), never torn.

class AudioCapture : public AudioStream
{
  public:
    static constexpr int kMaxChannels { 16 };

    AudioCapture() : AudioStream(kMaxChannels, queues_)
    {
    }
    ~AudioCapture()
    {
        end();
    }

    // frame_size: power of two >= 128; hop: multiple of 128, <= frame_size.
    // Allocates the ring (2 * frame_size per channel); init-time only.
    bool begin(int n_channels, int frame_size, int hop);
    void end();

    // True once frame_size + n*hop samples have arrived. Realigns (and counts
    // an overrun) if the pending frame was overwritten before being read.
    bool frameReady();

    // Copies the pending frame for channel ch as float in [-1, 1).
    // Only valid between frameReady() == true and consumeFrame().
    void readFrame(int ch, float* dst) const;

    // Advances the pending frame by hop.
    void consumeFrame()
    {
        frame_end_ += hop_;
    }

    uint32_t overruns() const
    {
        return overruns_;
    }

    virtual void update() override;

  private:
    audio_block_t* queues_[kMaxChannels];
    int16_t* ring_ {}; // [n_channels][capacity]
    int n_ch_ {};
    int frame_ {};
    int hop_ {};
    uint32_t cap_ {};              // ring capacity per channel, power of two
    volatile uint32_t written_ {}; // total samples per channel (ISR-written)
    uint32_t frame_end_ {};        // absolute index where the pending frame ends
    uint32_t overruns_ {};
    volatile bool active_ {};
};
