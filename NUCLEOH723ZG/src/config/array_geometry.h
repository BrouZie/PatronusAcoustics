#ifndef ARRAY_GEOMETRY_H
#define ARRAY_GEOMETRY_H

// ============================================================================
// Where the microphones physically are.
//
// This is the file you edit when the array changes. Positions are METRES in
// the array frame, one {x, y, z} row per microphone, ordered to match the TDM
// slot order the driver delivers (slot 0 -> row 0).
//
//   +z is BORESIGHT -- the direction the array is aimed.
//   +x, +y span the plane of the ring.
//
// That convention is shared with py-simulation/src/geometry.py, so a geometry
// can be pasted between the two and both will agree on what a bearing means.
//
// LEAF HEADER: no HAL, no function declarations, no module headers.
//
// Each block also declares the SEARCH GRID and FREQUENCY BAND that geometry can
// support, because both follow from the layout and nothing else:
//
//   ARRAY_SEARCH_* -- an array resolves as many angles as its aperture spans
//                     dimensions. A LINE spans one, so it fixes elevation and
//                     sweeps a single angle; a PLANE spans two. Searching more
//                     angles than the geometry supports adds no information, it
//                     just spreads one answer over equally-good cells and lets
//                     the reported bearing wander between them.
//
//   ARRAY_BAND_*   -- two mics d apart cannot tell a wavefront from its alias
//                     above c / (2 * d), d being the SMALLEST spacing, so the
//                     band's upper edge is set below that.
//
// Adding a geometry means adding all three together.
// ============================================================================

#include "audio_config.h"

#include <arm_math_types.h>

#if AUDIO_MIC_COUNT == 1

/* Placeholder so a default single-mic build still compiles. One microphone
 * carries no phase difference, so the SRP map comes out perfectly flat. */
static const float32_t ARRAY_MIC_POSITIONS[AUDIO_MIC_COUNT][3] = {
    { 0.000000f, 0.000000f, 0.000000f },
};

/* Nothing to search: one microphone resolves no directions at all. */
#define ARRAY_SEARCH_AZ_START_DEG 0.0f
#define ARRAY_SEARCH_AZ_STEP_DEG  1.0f
#define ARRAY_SEARCH_AZ_STEPS     1U
#define ARRAY_SEARCH_EL_START_DEG 90.0f
#define ARRAY_SEARCH_EL_STEP_DEG  1.0f
#define ARRAY_SEARCH_EL_STEPS     1U

#define ARRAY_BAND_MIN_HZ 300U
#define ARRAY_BAND_MAX_HZ 1500U

#elif AUDIO_MIC_COUNT == 2

/* Two mics on the x axis, 0.10 m apart.  f_alias = 1715 Hz.
 *
 * A pair resolves only the angle to its own axis, so the SRP map shows a
 * CONE of confusion -- a ring of equally-good directions, not a point. That
 * is the geometry talking, not a bug; three non-collinear mics are the
 * minimum for a unique bearing. */
static const float32_t ARRAY_MIC_POSITIONS[AUDIO_MIC_COUNT][3] = {
    { -0.050000f, 0.000000f, 0.000000f },
    { +0.050000f, 0.000000f, 0.000000f },
};

/* ONE angle, swept 0..180 deg in the z = 0 plane.
 *
 * A pair measures the angle between the source and its own axis and nothing
 * else, so elevation is held FIXED and azimuth carries the whole answer:
 * 0 and 180 deg lie along the axis (endfire), 90 deg is broadside. A source
 * above the plane reads as the in-plane direction with the same axis angle,
 * which loses nothing -- the pair could never have told those two apart.
 *
 * 0..180 covers the full range of arrival delay (-14..+14 samples at 10 cm)
 * exactly once, so no two cells of the grid mean the same thing. */
#define ARRAY_SEARCH_AZ_START_DEG 0.0f
#define ARRAY_SEARCH_AZ_STEP_DEG  5.0f
#define ARRAY_SEARCH_AZ_STEPS     37U
#define ARRAY_SEARCH_EL_START_DEG 90.0f
#define ARRAY_SEARCH_EL_STEP_DEG  5.0f
#define ARRAY_SEARCH_EL_STEPS     1U

#define ARRAY_BAND_MIN_HZ 300U
#define ARRAY_BAND_MAX_HZ 1700U // f_alias = 1715 Hz

#elif AUDIO_MIC_COUNT == 4

/* Uniform circular array, r = 0.085 m, in the z = 0 plane.
 * Adjacent spacing r*sqrt(2) = 0.1202 m -> f_alias = 1427 Hz. */
static const float32_t ARRAY_MIC_POSITIONS[AUDIO_MIC_COUNT][3] = {
    { +0.085000f, +0.000000f, 0.000000f }, //   0 deg
    { +0.000000f, +0.085000f, 0.000000f }, //  90 deg
    { -0.085000f, +0.000000f, 0.000000f }, // 180 deg
    { +0.000000f, -0.085000f, 0.000000f }, // 270 deg
};

/* A plane spans two dimensions, so azimuth and elevation are both real
 * answers here. Still mirror-symmetric about z = 0: a source 30 deg above the
 * plane and one 30 deg below produce the same map, which is why elevation
 * stops at the plane instead of continuing to 180. */
#define ARRAY_SEARCH_AZ_START_DEG 0.0f
#define ARRAY_SEARCH_AZ_STEP_DEG  5.0f
#define ARRAY_SEARCH_AZ_STEPS     72U // 0 .. 355 deg
#define ARRAY_SEARCH_EL_START_DEG 0.0f
#define ARRAY_SEARCH_EL_STEP_DEG  5.0f
#define ARRAY_SEARCH_EL_STEPS     19U // 0 .. 90 deg

#define ARRAY_BAND_MIN_HZ 300U
#define ARRAY_BAND_MAX_HZ 1400U // f_alias = 1427 Hz

#elif AUDIO_MIC_COUNT == 8

/* Uniform circular array, r = 0.17 m -- the inner ring of the station design.
 * Adjacent chord 2*r*sin(pi/8) = 0.1301 m -> f_alias = 1318 Hz.
 *
 * Planar, so it is mirror-symmetric about its own plane: a source 30 deg in
 * front and one 30 deg behind produce the same map. Breaking that is what the
 * second, axially offset ring in the design is for -- give the two rings
 * different z here once they exist. */
static const float32_t ARRAY_MIC_POSITIONS[AUDIO_MIC_COUNT][3] = {
    { +0.170000f, +0.000000f, 0.000000f }, //   0 deg
    { +0.120208f, +0.120208f, 0.000000f }, //  45 deg
    { +0.000000f, +0.170000f, 0.000000f }, //  90 deg
    { -0.120208f, +0.120208f, 0.000000f }, // 135 deg
    { -0.170000f, +0.000000f, 0.000000f }, // 180 deg
    { -0.120208f, -0.120208f, 0.000000f }, // 225 deg
    { +0.000000f, -0.170000f, 0.000000f }, // 270 deg
    { +0.120208f, -0.120208f, 0.000000f }, // 315 deg
};

// Planar, so azimuth and elevation both resolve, mirrored about the ring plane.
#define ARRAY_SEARCH_AZ_START_DEG 0.0f
#define ARRAY_SEARCH_AZ_STEP_DEG  5.0f
#define ARRAY_SEARCH_AZ_STEPS     72U // 0 .. 355 deg
#define ARRAY_SEARCH_EL_START_DEG 0.0f
#define ARRAY_SEARCH_EL_STEP_DEG  5.0f
#define ARRAY_SEARCH_EL_STEPS     19U // 0 .. 90 deg

#define ARRAY_BAND_MIN_HZ 300U
#define ARRAY_BAND_MAX_HZ 1300U // f_alias = 1318 Hz

#else
#error "No microphone position table for this AUDIO_MIC_COUNT -- add one to src/config/array_geometry.h"
#endif

#endif
