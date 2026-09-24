"""
Electrode Spacing Calculator - Bucketed Azimuth Version
----------------------------------------------------------
Same core logic as before (spacing in meters -> decimal degrees), but here
the azimuth is classified into one of 36 fixed 10-degree bins (0-10, 10-20,
... 350-360). Each bin uses its mid-point azimuth as a fixed reference angle
to compute the North/East split and the resulting conversion factor.

This trades a bit of precision (azimuth is rounded to its 10-degree bucket's
midpoint) for a simple, predictable lookup-table style behavior - useful if
you want consistent, reusable conversion factors across many profile lines
that fall in the same general direction.

Takes all inputs at once: profile length, number of electrodes, azimuth,
latitude.
"""

import math


def get_m_per_deg(latitude_deg):
    """WGS84-based meters-per-degree for latitude and longitude at a given latitude."""
    lat_rad = math.radians(latitude_deg)
    m_per_deg_lat = (111132.92
                      - 559.82 * math.cos(2 * lat_rad)
                      + 1.175 * math.cos(4 * lat_rad)
                      - 0.0023 * math.cos(6 * lat_rad))
    m_per_deg_lon = (111412.84 * math.cos(lat_rad)
                      - 93.5 * math.cos(3 * lat_rad)
                      + 0.118 * math.cos(5 * lat_rad))
    return m_per_deg_lat, m_per_deg_lon


def get_azimuth_bucket(azimuth_deg):
    """
    Classifies azimuth into one of 36 x 10-degree bins (0-360) and returns
    the bin's mid-point azimuth (used as the reference angle for that range)
    plus a readable label.
    """
    az = azimuth_deg % 360  # normalize into 0-360

    if 0 <= az < 10:
        az_ref = 5
    elif 10 <= az < 20:
        az_ref = 15
    elif 20 <= az < 30:
        az_ref = 25
    elif 30 <= az < 40:
        az_ref = 35
    elif 40 <= az < 50:
        az_ref = 45
    elif 50 <= az < 60:
        az_ref = 55
    elif 60 <= az < 70:
        az_ref = 65
    elif 70 <= az < 80:
        az_ref = 75
    elif 80 <= az < 90:
        az_ref = 85
    elif 90 <= az < 100:
        az_ref = 95
    elif 100 <= az < 110:
        az_ref = 105
    elif 110 <= az < 120:
        az_ref = 115
    elif 120 <= az < 130:
        az_ref = 125
    elif 130 <= az < 140:
        az_ref = 135
    elif 140 <= az < 150:
        az_ref = 145
    elif 150 <= az < 160:
        az_ref = 155
    elif 160 <= az < 170:
        az_ref = 165
    elif 170 <= az < 180:
        az_ref = 175
    elif 180 <= az < 190:
        az_ref = 185
    elif 190 <= az < 200:
        az_ref = 195
    elif 200 <= az < 210:
        az_ref = 205
    elif 210 <= az < 220:
        az_ref = 215
    elif 220 <= az < 230:
        az_ref = 225
    elif 230 <= az < 240:
        az_ref = 235
    elif 240 <= az < 250:
        az_ref = 245
    elif 250 <= az < 260:
        az_ref = 255
    elif 260 <= az < 270:
        az_ref = 265
    elif 270 <= az < 280:
        az_ref = 275
    elif 280 <= az < 290:
        az_ref = 285
    elif 290 <= az < 300:
        az_ref = 295
    elif 300 <= az < 310:
        az_ref = 305
    elif 310 <= az < 320:
        az_ref = 315
    elif 320 <= az < 330:
        az_ref = 325
    elif 330 <= az < 340:
        az_ref = 335
    elif 340 <= az < 350:
        az_ref = 345
    else:  # 350 <= az < 360
        az_ref = 355

    bucket_label = f"{int(az_ref - 5)}-{int(az_ref + 5)} deg"
    return az_ref, bucket_label


def calculate_electrode_spacing(profile_length_m, num_electrodes, azimuth_deg, latitude_deg):
    # Step 1: spacing in meters
    spacing_m = profile_length_m / num_electrodes

    # Step 2: pick the 10-degree azimuth bucket and its representative angle
    az_ref, bucket_label = get_azimuth_bucket(azimuth_deg)
    az_rad = math.radians(az_ref)

    # Step 3: decompose spacing into North/East components using the bucket's angle
    dN = spacing_m * math.cos(az_rad)
    dE = spacing_m * math.sin(az_rad)

    # Step 4: meters-per-degree at this latitude
    m_per_deg_lat, m_per_deg_lon = get_m_per_deg(latitude_deg)

    # Step 5: convert components to decimal degrees
    dLat_deg = dN / m_per_deg_lat
    dLon_deg = dE / m_per_deg_lon

    # Step 6: resultant spacing in decimal degrees
    spacing_deg = math.hypot(dLat_deg, dLon_deg)

    # Step 7: conversion factor for this bucket/latitude (deg -> m)
    conversion_factor = spacing_m / spacing_deg if spacing_deg != 0 else 0

    return {
        "spacing_m": spacing_m,
        "spacing_deg": spacing_deg,
        "conversion_factor_deg_to_m": conversion_factor,
        "azimuth_bucket": bucket_label,
        "azimuth_ref_used": az_ref,
        "m_per_deg_lat": m_per_deg_lat,
        "m_per_deg_lon": m_per_deg_lon,
    }


if __name__ == "__main__":
    print("=== Electrode Spacing Calculator (Bucketed Azimuth Version) ===")
    print("Enter values in this order, space-separated:")
    print("profile_length_m  number_of_electrodes  azimuth_deg  latitude_deg\n")

    raw = input("Input all values: ").split()
    profile_length, num_electrodes, azimuth, latitude = map(float, raw)
    num_electrodes = int(num_electrodes)

    result = calculate_electrode_spacing(profile_length, num_electrodes, azimuth, latitude)

    print("\n--- Results ---")
    print(f"Spacing (meters):            {result['spacing_m']:.4f} m")
    print(f"Azimuth bucket used:         {result['azimuth_bucket']} "
          f"(reference angle = {result['azimuth_ref_used']} deg)")
    print(f"Spacing (decimal degrees):   {result['spacing_deg']:.8f} deg")
    print(f"Meters per degree latitude:  {result['m_per_deg_lat']:.2f} m")
    print(f"Meters per degree longitude: {result['m_per_deg_lon']:.2f} m")
    print(f"Conversion factor (deg -> m): 1 deg = {result['conversion_factor_deg_to_m']:.4f} m")