#include "AudioCapture.hpp"

#include <new>
#include <string.h>

bool AudioCapture::begin(int n_channels, int frame_size, int hop)
{
    end();
    if (n_channels < 1 || n_channels > kMaxChannels)
        return false;
    if (frame_size < AUDIO_BLOCK_SAMPLES || (frame_size & (frame_size - 1)) != 0)
        return false;
    if (hop < AUDIO_BLOCK_SAMPLES || hop > frame_size || hop % AUDIO_BLOCK_SAMPLES != 0)
        return false;

    cap_  = 2 * (uint32_t)frame_size;
    ring_ = new (std::nothrow) int16_t[(size_t)n_channels * cap_];
    if (!ring_)
        return false;
    memset(ring_, 0, (size_t)n_channels * cap_ * sizeof(int16_t));

    n_ch_      = n_channels;
    frame_     = frame_size;
    hop_       = hop;
    written_   = 0;
    frame_end_ = frame_size;
    overruns_  = 0;
    active_    = true; // last: update() may already be running
    return true;
}

void AudioCapture::end()
{
    active_ = false;
    delete[] ring_;
    ring_ = nullptr;
}

void AudioCapture::update()
{
    audio_block_t* blk[kMaxChannels];
    for (int ch {}; ch < kMaxChannels; ++ch)
        blk[ch] = receiveReadOnly(ch);

    if (active_)
    {
        uint32_t idx { written_ & (cap_ - 1) }; // cap_ is a multiple of 128,
                                                // so a block never wraps
        for (int ch {}; ch < n_ch_; ++ch)
        {
            int16_t* dst { ring_ + (size_t)ch * cap_ + idx };
            if (blk[ch])
                memcpy(dst, blk[ch]->data, AUDIO_BLOCK_SAMPLES * sizeof(int16_t));
            else
                memset(dst, 0, AUDIO_BLOCK_SAMPLES * sizeof(int16_t));
        }
        written_ = written_ + AUDIO_BLOCK_SAMPLES;
    }

    for (int ch {}; ch < kMaxChannels; ++ch)
        if (blk[ch])
            release(blk[ch]);
}

bool AudioCapture::frameReady()
{
    if (!active_)
        return false;
    uint32_t w { written_ };
    if ((int32_t)(w - frame_end_) < 0)
        return false;
    // Oldest sample of the pending frame is frame_end_ - frame_; it must
    // still be inside the ring's valid window [w - cap_, w).
    if (w - frame_end_ > cap_ - (uint32_t)frame_)
    {
        ++overruns_;
        frame_end_ = w; // drop to the freshest complete frame
    }
    return true;
}

void AudioCapture::readFrame(int ch, float* dst) const
{
    constexpr float kScale { 1.0f / 32768.0f };
    uint32_t base { frame_end_ - (uint32_t)frame_ };
    const int16_t* src { ring_ + (size_t)ch * cap_ };
    for (int i {}; i < frame_; ++i)
        dst[i] = src[(base + i) & (cap_ - 1)] * kScale;
}
