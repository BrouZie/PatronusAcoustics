// NB: Units are in METERS and array should be defined in WS order!
#pragma once

// Hand-maintained mic-array geometries. EDIT THESE to match the physical build.
//
// Conventions (match py-simulation/src/geometry.py):
//   - positions in meters, array frame: +z = boresight, x/y = array plane
//   - mics listed in TDM daisy-chain order: entry i is the mic on TDM slot i
//     (Audio-library output channel 2*i)
// A partially populated array is valid: selecting n < n_mics at launch uses the
// first n entries, so list the mics you actually solder first.

namespace ArrayGeometry
{
struct Geometry
{
    const char* name;
    const float (*positions)[3]; // [n_mics][3] xyz, meters
    int n_mics;
};

inline constexpr float kCos45 { 0.70710678f };

// CURRENT ARRAY CONFIGURATION
// Breadboard bring-up: measured positions, daisy-chain order. NOTE: EDIT ME!!!!
inline constexpr float kBreadboard5[5][3] {
    { 0.000f, 0.000f, 0.0f }, // mic 0 (first WS in chain)
    { 0.120f, 0.000f, 0.0f }, // mic 1
    { 0.120f, 0.125f, 0.0f }, // mic 2
    { 0.000f, 0.130f, 0.0f }, // mic 3
    { 0.060f, 0.065f, 0.0f }, // mic 4 (center)
};

// Single ring, 8 mics, radius 8.5 cm (the 17 cm "inner" ring), plane z = 0.
// Mic k at azimuth k * 45deg, counter-clockwise from +x.
inline constexpr float kRing8[8][3] {
    { 0.085f, 0.0f, 0.0f },  { 0.085f * kCos45, 0.085f * kCos45, 0.0f },
    { 0.0f, 0.085f, 0.0f },  { -0.085f * kCos45, 0.085f * kCos45, 0.0f },
    { -0.085f, 0.0f, 0.0f }, { -0.085f * kCos45, -0.085f * kCos45, 0.0f },
    { 0.0f, -0.085f, 0.0f }, { 0.085f * kCos45, -0.085f * kCos45, 0.0f },
};

// Dual ring, 16 mics: inner r=8.5 cm at z=+5 cm (front), outer r=17 cm at
// z=-5 cm (back), 10 cm axial separation. Mics 0-7 inner, 8-15 outer,
// outer ring rotated 22.5deg for interleaved azimuth coverage.
inline constexpr float kCos225 { 0.92387953f };
inline constexpr float kSin225 { 0.38268343f };
inline constexpr float kDualRing16[16][3] {
    { 0.085f, 0.0f, 0.05f },
    { 0.085f * kCos45, 0.085f * kCos45, 0.05f },
    { 0.0f, 0.085f, 0.05f },
    { -0.085f * kCos45, 0.085f * kCos45, 0.05f },
    { -0.085f, 0.0f, 0.05f },
    { -0.085f * kCos45, -0.085f * kCos45, 0.05f },
    { 0.0f, -0.085f, 0.05f },
    { 0.085f * kCos45, -0.085f * kCos45, 0.05f },
    { 0.17f * kCos225, 0.17f * kSin225, -0.05f },
    { 0.17f * kSin225, 0.17f * kCos225, -0.05f },
    { 0.17f * -kSin225, 0.17f * kCos225, -0.05f },
    { 0.17f * -kCos225, 0.17f * kSin225, -0.05f },
    { 0.17f * -kCos225, 0.17f * -kSin225, -0.05f },
    { 0.17f * -kSin225, 0.17f * -kCos225, -0.05f },
    { 0.17f * kSin225, 0.17f * -kCos225, -0.05f },
    { 0.17f * kCos225, 0.17f * -kSin225, -0.05f },
};

inline constexpr Geometry kGeometries[] {
    { "ring8 r=8.5cm", kRing8, 8 },
    { "dualring16 r=8.5/17cm dz=10cm", kDualRing16, 16 },
	{ "breadboard-ring5 (uncertain/EDIT ME)", kBreadboard5, 5},
};
inline constexpr int kGeometryCount { static_cast<int>(sizeof(kGeometries) /
                                                       sizeof(kGeometries[0])) };
} // namespace ArrayGeometry
