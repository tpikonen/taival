import re
from math import radians, degrees, cos, sin, asin, sqrt

def ddl_merge(m1, m2):
    """Merge two defaultdict(list) values."""
    for k, v in m2.items():
        if isinstance(v, list):
            m1[k].extend(v)
        else:
            m1[k].append(v)


def ddl_uniq_key_merge(m1, m2, ukey):
    """Merge two defaultdict(list) instances with dict elements,
    if the key ukey is already present in some of the dicts in the value list,
    ignore the value"""
    for k, v in m2.items():
        if isinstance(v, list):
            for e1 in v:
                if not e1[ukey] in [ e2[ukey] for e2 in m1[k] ]:
                    m1[k].append(e1)
        else:
            if not v[ukey] in [ e[ukey] for e in m1[k] ]:
                m1[k].append(v)


def linesortkey(x):
    """Key function for list.sort() for correct line name sorting."""
    return (len([c for c in x if c.isdigit()]), x)


# Haversine function nicked from: https://stackoverflow.com/questions/4913349/haversine-formula-in-python-bearing-and-distance-between-two-gps-points
def haversine(p1, p2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    (lat1, lon1) = (p1[0], p1[1])
    (lat2, lon2) = (p2[0], p2[1])
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371 # Radius of earth in kilometers. Use 3956 for miles
    return c * r


def inv_haversine(d):
    """Return latitude difference in degrees of a north-south distance d.
    Can be used as an approximate inverse of haversine function."""
    r = 6371 # Radius of earth in kilometers. Use 3956 for miles
    return degrees(d/r)


def test_osm_shapes_have_v1_roles(rels):
    """Return True any of the relations in rels contain members with
    'forward' or 'backward' roles."""
    return any(mem.role == 'forward' or mem.role == 'backward'
        for r in rels for mem in r.members)


def ldist2(p1, p2):
    """Return distance metric squared for two latlon pairs."""
    d = (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2
    return d


def interp_shape(s, tol=10):
    """Given shape s defined as a list of latlon pairs, return a new shape
    with at a distance of no more than tol (meters) between points. New
    points are added with linear interpolation."""
    ltol = inv_haversine(tol/1000.0)
    ltol2 = ltol**2
    sout = [s[0]]
    for i in range(len(s)-1):
        d2 = ldist2(s[i], s[i+1])
        if d2 < ltol2:
            sout.append(s[i+1])
            continue
        d = sqrt(d2)
        n = int(d/ltol)+1
        v = [(s[i+1][0] - s[i][0])/float(n), (s[i+1][1] - s[i][1])/float(n)]
        for j in range(1,n):
            sout.append([s[i][0] + float(j)*v[0], s[i][1] + float(j)*v[1]])
        sout.append(s[i+1])
    return sout


# FIXME: Return also maximum deviation of the shape points or other stats.
def test_shape_overlap(s1, s2, tol=10.0, return_list=False):
    """Return the fraction [0...1.0] by which shape s1 overlaps s2 with
    tolerance tol (meters)."""
    p = interp_shape(s2, tol/2.0)
    ltol2 = inv_haversine(tol/2000.0)**2.0
    startm = 0
    overlaps = []
    for s in s1:
        found = False
        for m in list(range(startm, len(p))) + list(range(0, startm)):
            if ldist2(s, p[m]) < ltol2:
                found = True
                startm = m
                break
        if found:
            overlaps.append(1)
        else:
            overlaps.append(0)
    if return_list:
        return overlaps
    else:
        return float(sum(overlaps))/len(s1)


def arrivals2intervals(arrivals, peakhours=None, nighthours=None):
    """Service intervals in minutes from daily arrivals to a stop given in
    seconds since midnight. Returns a tuple of three sorted interval lists
    (normal, peak, night). 'peak' or 'night' are None if peakhours or
    nighthours are not given."""
    if peakhours:
        peak = [(3600*h[0], 3600*h[1]) for h in peakhours]
    else:
        peak = None
    if nighthours:
        night = [(3600*h[0], 3600*h[1]) for h in nighthours]
    else:
        night = None
    inorms = []
    ipeaks = []
    inights = []
    for i in range(len(arrivals)-1):
        ival = (arrivals[i+1] - arrivals[i]) // 60
        # Correct for times > 24 * 60 * 60 s
        tval = arrivals[i] if arrivals[i] < 24*3600 else arrivals[i] - 24*3600
        if peak and any(tval >= h[0] and tval <= h[1] for h in peak):
            ipeaks.append(ival)
        elif night and any(tval >= h[0] and tval <= h[1] for h in night):
            inights.append(ival)
        else:
            inorms.append(ival)
    inorms.sort()
    ipeaks.sort()
    inights.sort()
    #print("inorms: %s" % (str(inorms)))
    #print("ipeaks: %s" % (str(ipeaks)))
    #print("inights: %s" % (str(inights)))
    return (inorms, ipeaks, inights)

