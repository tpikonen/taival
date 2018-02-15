import requests, json
from taival import write_gpx

# HSL data from GraphQL API

# Digitransit API modes: BUS, RAIL, TRAM, SUBWAY, FERRY
mode_osm2hsl = {
    "train":    "RAIL",
    "subway":   "SUBWAY",
    "monorail": "",
    "tram":     "TRAM",
    "bus":      "BUS",
    "trolleybus": "",
    "aerialway": "",
    "ferry":    "FERRY"
}

hslurl = "https://api.digitransit.fi/routing/v1/routers/hsl/index/graphql"
headers = {'Content-type': 'application/graphql'}

def hsl_tags(lineref):
    """Return a dict with tag-like info for a route with given lineref."""
    query = '{routes(name:"%s") {shortName\nlongName\nmode\ntype\ndesc\ncolor\ntextColor\nbikesAllowed\nid\nurl\ngtfsId\n}}' % (lineref)
    r = requests.post(url=hslurl, data=query, headers=headers)
    data = json.loads(r.text)["data"]["routes"]
    for d in data:
        if d.get("shortName", "") == lineref:
            return d
    return []


def hsl_patterns(lineid, mode="bus"):
    """Return a list of pattern codes corresponding to a given line ID."""
    query = '{routes(name:"%s", modes:"%s") {\nshortName\npatterns {code}}}' \
        % (lineid, mode_osm2hsl[mode])
    #print(query)
    r = requests.post(url=hslurl, data=query, headers=headers)
    #print(r.text)
    rts = json.loads(r.text)["data"]["routes"]
    patterns = [r["patterns"] for r in rts if r["shortName"] == lineid]
    if patterns:
        codes = [d["code"] for d in patterns[0]]
    else:
        codes = []
    return codes


def hsl_patterns_for_date(lineid, datestr, mode="bus"):
    """Get patterns which are valid (have trips) on a date given in
    YYYYMMDD format."""
    codes = hsl_patterns(lineid, mode=mode)
    valids = []
    for c in codes:
        query = '{pattern(id:"%s"){tripsForDate(serviceDate:"%s"){id}}}' \
          % (c, datestr)
        r = requests.post(url=hslurl, data=query, headers=headers)
        if len(json.loads(r.text)["data"]["pattern"]["tripsForDate"]) > 0:
            valids.append(c)
    return valids


def hsl_patterns_after_date(lineid, datestr, mode="bus"):
    """Get patterns which are valid (have trips) after a date given in
    YYYYMMDD format. Can be used to discard patterns which not valid
    any more."""
    codes = hsl_patterns(lineid, mode=mode)
    valids = []
    dateint = int(datestr)
    for c in codes:
        query = '{pattern(id:"%s"){trips{activeDates}}}' % (c)
        r = requests.post(url=hslurl, data=query, headers=headers)
        trips = json.loads(r.text)["data"]["pattern"]["trips"]
        for t in trips:
           if any(int(d) > dateint for d in t["activeDates"]):
                valids.append(c)
                break
    return valids


def hsl_shape(code):
    """Return geometry for given pattern code as tuple (directionId, latlon)."""
    query = '{pattern(id:"%s") {directionId\ngeometry {lat\nlon}}}' % (code)
    #print(query)
    r = requests.post(url=hslurl, data=query, headers=headers)
    #print(r.text)
    pat = json.loads(r.text)["data"]["pattern"]
    dirid = pat["directionId"] # int
    latlon = [[c["lat"], c["lon"]] for c in pat["geometry"]]
    return (dirid, latlon)


def hsl_platforms(code):
    """Return stops for a given pattern code as waypoint list
    [[lat, lon, stopcode, name]]."""
    query = '{pattern(id:"%s") {stops {code\nname\nlat\nlon}}}' % (code)
    #print(query)
    r = requests.post(url=hslurl, data=query, headers=headers)
    #print(r.text)
    stops = json.loads(r.text)["data"]["pattern"]["stops"]
    return [[s["lat"], s["lon"], s["code"], s["name"]] for s in stops]


def hsl_gtfsid2url(gtfs):
    return "https://www.reittiopas.fi/linjat/" + str(gtfs)


def hsl_pattern2url(code):
    return "https://www.reittiopas.fi/linjat/" \
        + ":".join(code.split(':')[:2]) +"/pysakit/" + str(code)


def hsl_all_linerefs(mode="bus"):
    """Return a lineref:url dict of all linerefs for a given mode.
    URL points to a reittiopas page for the line."""
    query = '{routes(modes:"%s"){shortName\ntype\ngtfsId\n}}' \
        %(mode_osm2hsl[mode])
    r = requests.post(url=hslurl, data=query, headers=headers)
    rts = json.loads(r.text)["data"]["routes"]
    # Also filter out taxibuses (lähibussit) (type == 704)
    #refs = [r["shortName"] for r in rts if r["type"] != 704]
    refs = {r["shortName"]:hsl_gtfsid2url(r["gtfsId"])
            for r in rts if r["type"] != 704}
    return refs


def hsl2gpx(lineref, mode="bus"):
    """Write gpx files for given lineref from HSL digitransit API data."""
    codes = hsl_patterns(lineref, mode)
    #print(codes)
    for c in codes:
        (dirid, latlon) = hsl_shape(c)
        stops = hsl_platforms(c)
        fname = "%s_hsl_%s_%d.gpx" % (lineref, c, dirid)
        write_gpx(latlon, fname, waypoints=stops)
        print(fname)
    if not codes:
        print("Line '%s' not found in HSL." % lineref)
