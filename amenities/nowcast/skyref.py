"""What the sky could be, so we can say what the deck is doing.

THE VOCABULARY, because four different things were being called "clear".

  BURN-OFF      the LOW deck -- marine layer or fog sitting on the water --
                goes away. This is what burnoff.py forecasts. It says nothing
                about cloud above it.
  BREAKING      sunbreaks appear. The hourly PEAK Kt rises even though the hour
                as a whole stays dull. A bright moment, not a changed sky.
  CLEAR         the whole column is gone: no low deck AND no significant mid or
                high cloud. Blue sky. This is what a member means by "clear",
                and it is rarer here than burn-off by a wide margin.
  UNMEASURABLE  the sun is too low for a pyranometer at this site to say
                anything at all. See the floor below.

Conflating the first two put "84% chance it clears by 3pm" on a public board for
a forecast that was only ever about the low deck. Conflating the first and third
made winter look like a season when nothing burns off.

THE FLOOR, AND IT IS NOT A DETAIL. Measured on hours when the model reports a
clear sky at EVERY level -- no low, mid or high cloud over the cove:

    sun elevation   Kt p50    p90     p99
      10-15 deg     0.187    0.354   0.484
      15-20 deg     0.375    0.712   1.497
      20-25 deg     0.583    0.964   1.290
      25-35 deg     0.832    1.058   1.297
      35-50 deg     0.921    1.053   1.191

At 10-15 degrees a CLOUDLESS sky reads Kt 0.19, and the 99th percentile never
reaches 0.5. That is not cloud. The cove sits in a narrow inlet between forested
hills, and at low sun the direct beam is behind the terrain; cheap pyranometers
also lose badly to cosine error at high incidence. Below about 25 degrees Kt
stops describing the sky and starts describing the horizon.

marine.py already carries QC_MIN_ELEV_DEG = 25.0 for pyranometer QC -- the right
number was known and marine.kt kept using MIN_ELEV_DEG = 10.0.

WHAT THAT COSTS: at 47.3 N the sun peaks at 22.8 deg in January, 22.7 in
November and 19.2 in December. **Those three months never clear the floor at
all.** Burn-off in deep winter is not measurable with these instruments, and no
correction fixes it -- you cannot divide your way out of the sun being behind a
hill. Saying so is the honest position; a ceilometer or a sky camera is the
instrument that would.

THE CORRECTION ITSELF, for the hours that are usable. Transmission is roughly
multiplicative, Kt = T_low x T_upper, so the deck's own transmission is

    T_low = Kt / achievable_kt(elevation, upper cloud)

Upper cloud is taken from Open-Meteo's cloud_cover_mid/high AT THE COVE. The
airfields cannot serve here: their p90 envelope is flat at ~1.0 whatever they
report, because at 23 km their high cloud is not our high cloud.
"""
import math

# Deck-free ceiling, from hours the model calls clear at every level.
_ELEV_REF = [(25, 1.00), (30, 1.06), (40, 1.05), (50, 1.00), (90, 1.00)]
# Upper-cloud transmission, from the p90 envelope by mid/high cover.
_UPPER_T = [(0, 1.00), (22, 0.97), (50, 0.97), (77, 0.90), (95, 0.77), (100, 0.77)]

USABLE_ELEV_DEG = 25.0     # matches marine.QC_MIN_ELEV_DEG; below this, decline
CLEAR_UPPER_PCT = 25.0     # mid/high at or under this counts as a clear column


def _interp(table, x):
    if x <= table[0][0]:
        return table[0][1]
    if x >= table[-1][0]:
        return table[-1][1]
    for (a, ya), (b, yb) in zip(table, table[1:]):
        if a <= x <= b:
            return ya + (yb - ya) * (x - a) / (b - a) if b > a else ya
    return table[-1][1]


def usable(elev_deg):
    """Can a pyranometer say anything about the sky at this sun angle here?"""
    return elev_deg is not None and elev_deg >= USABLE_ELEV_DEG


def achievable_kt(elev_deg, upper_pct):
    """Kt a deck-free cove would see now, given the cloud ABOVE the deck."""
    if not usable(elev_deg):
        return None
    return _interp(_ELEV_REF, elev_deg) * _interp(_UPPER_T, max(0.0, min(100.0, upper_pct or 0.0)))


def deck_transmission(kt, elev_deg, upper_pct):
    """Kt as a FRACTION of what today's upper sky allows -- the low deck alone.

    None when the sun is too low to judge, which is the honest answer rather
    than a number that would read as a very thick deck.
    """
    a = achievable_kt(elev_deg, upper_pct)
    if a is None or kt is None or a <= 0:
        return None
    return kt / a


def classify(kt, elev_deg, upper_pct, broke=0.65):
    """'unmeasurable' | 'deck' | 'burned_off' | 'clear' -- the vocabulary above."""
    if not usable(elev_deg):
        return "unmeasurable"
    t = deck_transmission(kt, elev_deg, upper_pct)
    if t is None:
        return "unmeasurable"
    if t < broke:
        return "deck"
    return "clear" if (upper_pct or 0.0) <= CLEAR_UPPER_PCT else "burned_off"
