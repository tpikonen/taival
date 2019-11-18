import requests, json, logging, time
from collections import defaultdict

# Obtain data from digitransit.fi GraphQL API

log = logging.getLogger(__name__)


def gtfsid2url(gtfs):
    return "https://www.reittiopas.fi/linjat/" + str(gtfs)


def pattern2url(code):
    return "https://www.reittiopas.fi/linjat/" \
        + ":".join(code.split(':')[:2]) +"/pysakit/" + str(code)


def terminalid2url(gtfs):
    return "https://reittiopas.hsl.fi/terminaalit/" + gtfs


def citybike2url(latlon):
    return "https://reittiopas.hsl.fi/::{},{}".format(latlon[0], latlon[1])

class Digitransit:
    def __init__(self, agency, url, modecolors=None, peakhours=None, \
      nighthours=None, shapetols=None):
        self.routedict_cache = {}
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
        self.shapetols = shapetols if shapetols \
          else { k: 30.0 for k in self.modecolors.keys() }
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


    def apiquery(self, query, max_tries=5):
        """
        Make a graphql query via requests.
        """
        ok = False
        tries = 0
        sleeptime = 10
        while tries < max_tries:
            try:
                tries += 1
                r = requests.post(url=self.url, data=query, headers=self.headers)
                r.raise_for_status()
            except (requests.exceptions.ConnectionError,
              requests.exceptions.HTTPError) as e:
                log.warning(f"Digitransit API query failed, waiting {sleeptime} secs and retrying...")
                time.sleep(sleeptime)
            finally:
                if r.status_code == requests.codes.ok:
                    break
        if tries >= max_tries:
            log.error(f"Failed to get a response from Digitransit API after {max_tries} attempts.")
        r.encoding = 'utf-8'
        return r


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


    # FIXME: Make routedict_cache a lineref->data dict
    def get_routedict(self, mode):
        """
        Return a (possibly cached) dict with tags and stops for all routes.
        """
        query = """{
    routes(transportModes:[%s]) {
        shortName
        longName
        mode
        type
        desc
        gtfsId
        patterns {
            code
            directionId
            stops {
                code
                name
                lat
                lon
            }
            geometry {
                lat
                lon
            }
        }
    }}""" % (self.mode_from_osm[mode])
        if mode in self.routedict_cache.keys():
            return self.routedict_cache[mode]
        else:
            log.debug(f"Running Digitransit.get_routedict('{mode}') query...")
            r = self.apiquery(query)
            data = json.loads(r.text)["data"]["routes"]
            self.routedict_cache[mode] = data
            return data


    def tags(self, lineref, mode):
        """Return a dict with tag-like info for a route with given lineref."""
        data = self.get_routedict(mode)
        for d in data:
            if d.get("shortName", "") == lineref:
                return d
        return []


    def tags_query(self, lineref, mode):
        """
        Return a dict with tag-like info for a route with given lineref
        from a separate API query.
        """
        query = '{routes(name:"%s") {shortName\nlongName\nmode\ntype\ndesc\ncolor\ntextColor\nbikesAllowed\nid\nurl\ngtfsId\n}}' % (lineref)
        r = self.apiquery(query)
        data = json.loads(r.text)["data"]["routes"]
        for d in data:
            if d.get("shortName", "") == lineref:
                return d


    def patterns_extra_query(self, lineref, mode, extrafields=[]):
        """
        Return a list of patterns with code and 'extrafields' fields
        corresponding to a given lineref and mode from a separate
        API query.
        """
        query = '{routes(name:"%s", transportModes:[%s]) {\nshortName\npatterns {code%s}}}' \
            % (lineref, self.mode_from_osm[mode],
                ("\n" + "\n".join(extrafields)) if extrafields else "")
        d = self.apiquery(query)
        rts = json.loads(d.text)["data"]["routes"]
        pats = [r["patterns"] for r in rts if r["shortName"] == lineref]
        out = pats[0] if pats and len(pats) > 0 else []
        return out


    def patterns(self, lineref, mode):
        """Return a list of patterns from a (cached) routedir
        corresponding to a given lineref and mode."""
        rts = self.get_routedict(mode)
        pats = [r["patterns"] for r in rts if r["shortName"] == lineref]
        out = pats[0] if pats and len(pats) > 0 else []
        return out


    def codes_query(self, lineid, mode="bus"):
        """
        Return a list of pattern codes corresponding to a given line ID
        from a separate API query.
        """
        pats = self.patterns_extra_query(lineid, mode)
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
        pats = self.patterns(lineid, mode)

        code0 = self._longest([p for p in pats if p["directionId"] == 0])
        code1 = self._longest([p for p in pats if p["directionId"] == 1])
        return code0 + code1


    @staticmethod
    def _match_stopcount(plist, stopcount):
        """
        Return a list of patterns codes with stop count closest to 'stopcount'.
        """
        out = []
        mindelta = 1e6
        for p in plist:
            delta = abs(len(p["stops"]) - stopcount)
            log.debug("code {}, delta = {}".format(p["code"], delta))
            if delta < mindelta:
                out = [p]
                mindelta = delta
            elif delta == mindelta:
                out.append(p)
        return [p["code"] for p in out]


    def codes_match_stopcount(self, lineid, stopcount, mode="bus"):
        """
        Return a list pattern codes for a line with the number of stops
        closes to the number given in 'stopcount'. The list includes the
        longest pattern per direction, i.e. at least two patterns. If two
        or more patterns have the same number of stops, both are returned.
        """
        pats = self.patterns(lineid, mode)
        code0 = self._match_stopcount([p for p in pats if p["directionId"] == 0], stopcount)
        code1 = self._match_stopcount([p for p in pats if p["directionId"] == 1], stopcount)
        return code0 + code1


    def codes_for_date(self, lineid, datestr, mode="bus"):
        """Get patterns which are valid (have trips) on a date given in
        YYYYMMDD format."""
        codes = self.patterns(lineid, mode)
        valids = []
        for c in codes:
            query = '{pattern(id:"%s"){tripsForDate(serviceDate:"%s"){id}}}' \
              % (c, datestr)
            r = self.apiquery(query)
            if len(json.loads(r.text)["data"]["pattern"]["tripsForDate"]) > 0:
                valids.append(c)
        return valids


    def patterns_after_date(self, lineid, mode, datestr):
        """Get patterns which are valid (have trips) after a date given in
        YYYYMMDD format. Can be used to discard patterns which are not valid
        any more."""
        pats = self.patterns(lineid, mode)
        valids = []
        dateint = int(datestr)
        for p in pats:
            c = p["code"]
            query = '{pattern(id:"%s"){trips{activeDates}}}' % (c)
            r = self.apiquery(query)
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
        pats = self.patterns_after_date(lineid, mode, datestr)
        return [p["code"] for p in pats]


    def codes_longest_after_date(self, lineid, datestr, mode="bus"):
        """Return a list of pattern codes which have the most stops and which
        are valid after a given date.
        The list includes the longest pattern per direction, i.e. at least
        two patterns. If two or more patterns have the same number of stops,
        both are returned."""
        pats = self.patterns_after_date(lineid, mode, datestr)

        code0 = self._longest([p for p in pats if p["directionId"] == 0])
        code1 = self._longest([p for p in pats if p["directionId"] == 1])
        return code0 + code1


    def shape(self, code, mode):
        """
        Return geometry from route cache for given pattern code as
        tuple (directionId, latlon).
        """
        # FIXME needs a code -> pattern dict
        rts = self.get_routedict(mode)
        pats = [ p for r in rts for p in r["patterns"] if p["code"] == code ]
        pat = pats[0]
        dirid = pat["directionId"] # int
        latlon = [[c["lat"], c["lon"]] for c in pat["geometry"]] \
          if ("geometry" in pat.keys() and pat["geometry"] is not None) else []
        return (dirid, latlon)


    def shape_query(self, code, mode):
        """
        Return geometry from a API query for given pattern code as
        tuple (directionId, latlon).
        """
        query = '{pattern(id:"%s") {directionId\ngeometry {lat\nlon}}}' % (code)
        r = self.apiquery(query)
        pat = json.loads(r.text)["data"]["pattern"]
        dirid = pat["directionId"] # int
        latlon = [[c["lat"], c["lon"]] for c in pat["geometry"]]
        return (dirid, latlon)


    def platforms_query(self, code):
        """
        Return stops for a given pattern code as waypoint list
        [[lat, lon, stopcode, name]] from a separate API query.
        """
        query = '{pattern(id:"%s") {stops {code\nname\nlat\nlon}}}' % (code)
        r = self.apiquery(query)
        stops = json.loads(r.text)["data"]["pattern"]["stops"]
        return [(s["lat"], s["lon"], s["code"], s["name"]) for s in stops]


    def platforms(self, code, mode):
        """
        Return platform tuple (lat, lon, code, name) from cached routes for
        a given pattern code as list.
        """
        routes = self.get_routedict(mode)
        # FIXME: make a pattern dict from cached data
        pats = [ p for r in routes for p in r["patterns"] if p["code"] == code ]
        stops = pats[0]["stops"]
        return [(s["lat"], s["lon"], s.get("code", "<no code>"), s["name"]) for s in stops]


    def all_linerefs(self, mode="bus"):
        """Return a lineref:url dict of all linerefs for a given mode.
        URL points to a reittiopas page for the line."""
        rts = self.get_routedict(mode)
        # Also filter out taxibuses (lähibussit) (type == 704)
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
        r = self.apiquery(query)
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
        r = self.apiquery(query)
        data = json.loads(r.text)["data"]["stops"]
        stops = defaultdict(dict)
        clusters = defaultdict(list) # cluster gtfsId -> ref list
        for d in data:
            ref = d.get("code", "")
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


    def stations(self):
        """Return all stations in a 'mode' -> list of stations dict."""
        query = """{
  stations {
    name
    gtfsId
    zoneId
    vehicleMode
    lat
    lon
  }
}"""
        r = self.apiquery(query)
        data = json.loads(r.text)["data"]["stations"]
        stations = defaultdict(list)
        for d in data:
            mode = self.mode_to_osm[d.pop("vehicleMode")]
            d["mode"] = mode
            d["latlon"] = (d.pop("lat"), d.pop("lon"))
            stations[mode].append(d)
        return stations


    def citybikes(self):
        """Return all citybike stations."""
        query = """{
  bikeRentalStations {
    name
    stationId
    bikesAvailable
    spacesAvailable
    state
    realtime
    lat
    lon
    networks
  }
}"""
        r = self.apiquery(query)
        data = json.loads(r.text)["data"]["bikeRentalStations"]
        cbs = {}
        for d in data:
#            d["capacity"] = d.pop('spacesAvailable', None)\
#              + d.pop('bikesAvailable', None)
            d["latlon"] = (d["lat"], d["lon"])
            d.pop('lat', None)
            d.pop('lon', None)
            cbs[d['stationId']] = d
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
        r = self.apiquery(query)
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

