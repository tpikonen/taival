import requests, json, logging
from collections import defaultdict

# Obtain data from digitransit.fi GraphQL API

log = logging.getLogger(__name__)


def gtfsid2url(gtfs):
    return "https://www.reittiopas.fi/linjat/" + str(gtfs)


def pattern2url(code):
    return "https://www.reittiopas.fi/linjat/" \
        + ":".join(code.split(':')[:2]) +"/pysakit/" + str(code)


class Digitransit:
    def __init__(self, agency, url, modecolors=None, peakhours=None, \
      nighthours=None):
        self.agency = agency
        self.url = url
        self.headers = {'Content-type': 'application/graphql'}
        # Source for colors: https://www.hsl.fi/tyyliopas/varit
        self.modecolors = {
            "bus": None,
            "tram":     None,
            "train":    None,
            "subway":   None,
            "ferry":    None,
            "aerialway": None,
            "monorail": None,
            "trolleybus": None
        }
        if modecolors is not None:
            self.modecolors = modecolors
        self.peakhours = self.normalize_hours(peakhours) if peakhours else None
        self.nighthours = self.normalize_hours(nighthours) if nighthours else None
        # Digitransit API transportModes: BUS, RAIL, TRAM, SUBWAY, FERRY
        self.mode_from_osm = {
            "train":    "RAIL",
            "subway":   "SUBWAY",
            "monorail": None,
            "tram":     "TRAM",
            "bus":      "BUS",
            "trolleybus": None,
            "aerialway": "FUNICULAR",
            "ferry":    "FERRY"
        }
        self.mode_to_osm = { v:k for (k,v) in self.mode_from_osm.items() if v }
        self.taxibus_refs = None

    # TODO: def apiquery(self, query):

    @staticmethod
    def normalize_hours(hours):
        outhours = []
        for v in hours:
            if not (v[0] < 24 and v[0] >= 0 and v[1] <= 24 and v[1] >= 0):
                raise ValueError
            if v[0] > v[1]:
                outhours.append((v[0], 24))
                outhours.append((0, v[1]))
            else:
                outhours.append(v)
        return outhours


    def tags(self, lineref):
        """Return a dict with tag-like info for a route with given lineref."""
        query = '{routes(name:"%s") {shortName\nlongName\nmode\ntype\ndesc\ncolor\ntextColor\nbikesAllowed\nid\nurl\ngtfsId\n}}' % (lineref)
        r = requests.post(url=self.url, data=query, headers=self.headers)
        r.raise_for_status()
        r.encoding = 'utf-8'
        data = json.loads(r.text)["data"]["routes"]
        for d in data:
            if d.get("shortName", "") == lineref:
                return d
        return []


    def patterns(self, lineid, mode="bus", extrafields=[]):
        """Return a list of patterns with 'code' and 'directionId' fields
        corresponding to a given line ID."""
        query = '{routes(name:"%s", transportModes:[%s]) {\nshortName\npatterns {code%s}}}' \
            % (lineid, self.mode_from_osm[mode],
                ("\n" + "\n".join(extrafields)) if extrafields else "")
        r = requests.post(url=self.url, data=query, headers=self.headers)
        r.raise_for_status()
        r.encoding = 'utf-8'
        rts = json.loads(r.text)["data"]["routes"]
        pats = [r["patterns"] for r in rts if r["shortName"] == lineid]
        out = pats[0] if pats and len(pats) > 0 else []
        return out


    def codes(self, lineid, mode="bus"):
        """Return a list of pattern codes corresponding to a given line ID."""
        pats = self.patterns(lineid, mode)
        return [d["code"] for d in pats]


    @staticmethod
    def _longest(plist):
        """Return a list of the pattern code(s) with longest stop list."""
        out = []
        maxlen = 0
        for p in plist:
            n = len(p["stops"])
            if n > maxlen:
                out = [p]
                maxlen = n
            elif n == maxlen:
                out.append(p)
        return [p["code"] for p in out]


    def codes_longest_per_direction(self, lineid, mode="bus"):
        """Return a list of pattern codes which have the most stops.
        The list includes the longest pattern per direction, i.e. at least
        two patterns. If two or more patterns have the same number of stops,
        both are returned."""
        pats = self.patterns(lineid, mode, ["directionId", "stops {id}"])

        code0 = self._longest([p for p in pats if p["directionId"] == 0])
        code1 = self._longest([p for p in pats if p["directionId"] == 1])
        return code0 + code1


    def codes_for_date(self, lineid, datestr, mode="bus"):
        """Get patterns which are valid (have trips) on a date given in
        YYYYMMDD format."""
        codes = self.patterns(lineid, mode=mode)
        valids = []
        for c in codes:
            query = '{pattern(id:"%s"){tripsForDate(serviceDate:"%s"){id}}}' \
              % (c, datestr)
            r = requests.post(url=self.url, data=query, headers=self.headers)
            r.raise_for_status()
            r.encoding = 'utf-8'
            if len(json.loads(r.text)["data"]["pattern"]["tripsForDate"]) > 0:
                valids.append(c)
        return valids


    def patterns_after_date(self, lineid, datestr, mode="bus", extrafields=[]):
        """Get patterns which are valid (have trips) after a date given in
        YYYYMMDD format. Can be used to discard patterns which are not valid
        any more."""
        pats = self.patterns(lineid, mode, extrafields)
        valids = []
        dateint = int(datestr)
        for p in pats:
            c = p["code"]
            query = '{pattern(id:"%s"){trips{activeDates}}}' % (c)
            r = requests.post(url=self.url, data=query, headers=self.headers)
            r.encoding = 'utf-8'
            r.raise_for_status()
            trips = json.loads(r.text)["data"]["pattern"]["trips"]
            for t in trips:
               if any(int(d) > dateint for d in t["activeDates"]):
                    valids.append(p)
                    break
        return valids


    def codes_after_date(self, lineid, datestr, mode="bus"):
        """Get pattern codes which are valid (have trips) after a date given in
        YYYYMMDD format. Can be used to discard patterns which are not valid
        any more."""
        pats = self.patterns_after_date(lineid, datestr, mode)
        return [p["code"] for p in pats]


    def codes_longest_after_date(self, lineid, datestr, mode="bus"):
        """Return a list of pattern codes which have the most stops and which
        are valid after a given date.
        The list includes the longest pattern per direction, i.e. at least
        two patterns. If two or more patterns have the same number of stops,
        both are returned."""
        pats = self.patterns_after_date(lineid, datestr, mode,
          ["directionId", "stops {id}"])

        code0 = self._longest([p for p in pats if p["directionId"] == 0])
        code1 = self._longest([p for p in pats if p["directionId"] == 1])
        return code0 + code1


    def shape(self, code):
        """
        Return geometry for given pattern code as tuple (directionId, latlon).
        """
        query = '{pattern(id:"%s") {directionId\ngeometry {lat\nlon}}}' % (code)
        r = requests.post(url=self.url, data=query, headers=self.headers)
        r.encoding = 'utf-8'
        r.raise_for_status()
        pat = json.loads(r.text)["data"]["pattern"]
        dirid = pat["directionId"] # int
        latlon = [[c["lat"], c["lon"]] for c in pat["geometry"]]
        return (dirid, latlon)


    def platforms(self, code):
        """Return stops for a given pattern code as waypoint list
        [[lat, lon, stopcode, name]]."""
        query = '{pattern(id:"%s") {stops {code\nname\nlat\nlon}}}' % (code)
        r = requests.post(url=self.url, data=query, headers=self.headers)
        r.raise_for_status()
        r.encoding = 'utf-8'
        stops = json.loads(r.text)["data"]["pattern"]["stops"]
        return [(s["lat"], s["lon"], s["code"], s["name"]) for s in stops]


    def all_linerefs(self, mode="bus"):
        """Return a lineref:url dict of all linerefs for a given mode.
        URL points to a reittiopas page for the line."""
        query = '{routes(transportModes:[%s]){shortName\ntype\ngtfsId\n}}' \
            %(self.mode_from_osm[mode])
        r = requests.post(url=self.url, data=query, headers=self.headers)
        r.raise_for_status()
        r.encoding = 'utf-8'
        rts = json.loads(r.text)["data"]["routes"]
        # Also filter out taxibuses (lähibussit) (type == 704)
        #refs = [r["shortName"] for r in rts if r["type"] != 704]
        refs = {r["shortName"]: gtfsid2url(r["gtfsId"])
                for r in rts if r["type"] != 704}
        self.taxibus_refs = {r["shortName"]: gtfsid2url(r["gtfsId"])
                for r in rts if r["type"] == 704}
        return refs


    def taxibus_linerefs(self, mode="bus"):
        if mode != "bus":
            return {}
        if self.taxibus_refs is None:
            _ = self.all_linerefs() # Gets taxibus_refs as a side effect
        return self.taxibus_refs


    def arrivals_for_date(self, code, datestr):
        """Return arrival times to the first stop of the given pattern at
        a given date."""
        query = '{pattern(id:"%s"){tripsForDate(serviceDate:"%s"){stoptimes{scheduledArrival}}}}' % (code, datestr)
        r = requests.post(url=self.url, data=query, headers=self.headers)
        r.raise_for_status()
        r.encoding = 'utf-8'
        alltimes = json.loads(r.text)["data"]["pattern"]["tripsForDate"]
        times = [t["stoptimes"][0]["scheduledArrival"] for t in alltimes]
        times.sort()
        return times


    def stops(self):
        """Return all stops in the network."""
        query = """
{
  stops {
    code
    gtfsId
    zoneId
    name
    parentStation {
      code
    }
    platformCode
    wheelchairBoarding
    vehicleMode
    cluster {
      gtfsId
      name
    }
    lat
    lon
  }
}
"""
        r = requests.post(url=self.url, data=query, headers=self.headers)
        r.raise_for_status()
        r.encoding = 'utf-8'
        data = json.loads(r.text)["data"]["stops"]
        stops = { k:{} for k in self.modecolors.keys() }
        clusters = defaultdict(list) # cluster gtfsId -> ref list
        for d in data:
            ref = d["code"]
            if not ref:
                continue
            d["mode"] = self.mode_to_osm[d['vehicleMode']]
            d.pop('vehicleMode', None)
            d["latlon"] = (d["lat"], d["lon"])
            d.pop('lat', None)
            d.pop('lon', None)
            stops[d["mode"]][ref] = d
            cref = d["cluster"]["gtfsId"]
            clusters[cref].append(ref)
        return (stops, clusters)


    def citybikes(self):
        """Return all citybike stations."""
        query = """{
  bikeRentalStations {
    name
    stationId
    bikesAvailable
    spacesAvailable
    lat
    lon
  }
}"""
        r = requests.post(url=self.url, data=query, headers=self.headers)
        r.raise_for_status()
        r.encoding = 'utf-8'
        data = json.loads(r.text)["data"]["bikeRentalStations"]
        cbs = []
        for d in data:
            d["capacity"] = d.pop('spacesAvailable', None)\
              + d.pop('bikesAvailable', None)
            d["latlon"] = (d["lat"], d["lon"])
            d.pop('lat', None)
            d.pop('lon', None)
            cbs.append(d)
        return cbs


    def bikeparks(self):
        """Return all bicycle parking spaces."""
        query = """{
  bikeParks {
    name
    bikeParkId
    spacesAvailable
    lat
    lon
  }
}"""
        r = requests.post(url=self.url, data=query, headers=self.headers)
        r.raise_for_status()
        r.encoding = 'utf-8'
        data = json.loads(r.text)["data"]["bikeParks"]
        bps = []
        for d in data:
            d["name"] = d["name"].replace(" (pyörä)", "")
            d["capacity"] = d.pop('spacesAvailable', None)
            d["latlon"] = (d["lat"], d["lon"])
            d.pop('lat', None)
            d.pop('lon', None)
            bps.append(d)
        return bps
