import difflib, sys
import osm
from util import *
from digitransit import pattern2url

outfile = None

def wr(*args, **kwargs):
    kwargs["file"] = outfile
    print(*args, **kwargs)


def test_tag(ts, key, value=None, badtag=False):
    """Test if a tag has a given value or just exists, if value=None."""
    if not key in ts.keys():
        if badtag:
            return
        wr("Tag '''%s''' not set " % key, end='')
        if value is not None:
            wr("(should be '%s').\n" % value)
        else:
            wr(".\n")
        return
    tval = ts[key]
    if badtag:
        wr("Probably '''mispelled''' tag '''%s''' with value '%s'.\n" \
          % (key, tval))
        return
    if value is None:
        return
    if tval != value:
        wr("Tag '''%s''' has value '%s' (should be '%s').\n" \
          % (key, tval, value))


def test_hsl_routename(ts, lineref, longname):
    """Do a special test for the route name-tag."""
    # Reittiopas longName field sometimes has dangling hyphens, remove them.
    longname = longname[1:] if longname[0] == '-' else longname
    longname = longname[:-1] if longname[-1] == '-' else longname
    stops = hsl_longname2stops(longname)
    name1 = lineref + " " + "–".join(stops) # Use en dash as a separator
    stops.reverse()
    name2 = lineref + " " + "–".join(stops)
    tag = ts.get("name", "")
    if tag == "":
        wr("Tag '''name''' not set (should be either '%s' or '%s').\n" \
          % (name1, name2))
    elif tag != name1 and tag != name2:
        wr("Tag '''name''' has value '%s' (should be either '%s' or '%s').\n" \
          % (tag, name1, name2))


def test_stop_positions(rel, mode="bus"):
    wr("'''Stop positions:'''\n")
    stops = [mem.resolve(resolve_missing=True) \
      for mem in rel.members if mem.role == "stop"]
    platforms = [mem.resolve(resolve_missing=True) \
      for mem in rel.members if mem.role == "platform"]
#    wr("Route [%s %s] '%s' " % (osm.relid2url(rel.id), rel.id, \
#      rel.tags.get("name", "<no-name-tag>")))
    wr("%d stop_positions vs. %d platforms." \
      % (len(stops), len(platforms)))
    wr("")
#    # FIXME: Output something sensible
#    for s in stops:
#        test_tag(s.tags, "ref")
#        test_tag(s.tags, "name")
#        test_tag(s.tags, "public_transport", "stop_position")
#        test_tag(s.tags, mode, "yes")
#    for p in platforms:
#        p_name = p.tags.get("name", "<platform-has-no-name>")
#        p_ref = p.tags.get("ref", "<platform-has-no-ref>")
#        refmatches = [s for s in stops \
#          if s.tags.get("ref", "") == p_ref]
#        namematches = [s for s in stops \
#          if s.tags.get("name", "") == p_name]
#        sout = " Platform %s %s:" % (p_ref, p_name)
#        linit = len(sout)
#        if len(refmatches) < 1:
#            sout += " No stop_position with matching ref!"
#        elif len(refmatches) > 1:
#            sout +=" More than one stop_position with matching ref!"
#        if len(namematches) < 1:
#            sout += " No stop_position with matching name!"
#        elif len(namematches) > 1:
#            sout += " More than one stop_position with matching name!"
#        if len(sout) > linit:
#            wr(sout)
    wr("")


def test_stop_locations():
    # start to complain if stop pos is farther than this from HSL platform
    # FIXME: Turn the comparison around and complain about HSL platforms
    # missing stop positions?
    tol = 0.050 # km FIXME: needs to be bigger for mode=subway?
    osmstops = [osm.stops(rel) for rel in rels]
    for r in range(len(osmstops)):
        wr("Route '%s'." % (rels[r].tags.get("name", "<no-name-tag>")))
        wr("Stops: %d in OSM vs. %d in HSL.\n" \
        % (len(osmstops[r]), len(hslplatforms[r])))
        for i in range(len(osmstops[r])):
            pdists = [haversine(osmstops[r][i][:2], hslplatforms[r][x][:2])
                for x in range(len(hslplatforms[r])) ]
            pind = pdists.index(min(pdists))
            mind = pdists[pind]
            if mind > tol:
                wr(" Distance from OSM stop %s to HSL platform %s (%s)" %
                  (osmstops[r][i][2], hslplatforms[r][pind][2], \
                  hslplatforms[r][pind][3], mind*1000, tol*1000))


def print_route_master(ld):
    """Test if a route_master relation for lineref exists and contains the
    given route_ids."""
    lineref = ld["lineref"]
    mode = ld["mode"]
    rm_rels = ld["rm_rels"]
    route_ids = [r.id for r in ld["rels"]]

    nr = len(rm_rels)
    wr("'''Route master:'''")
    if nr < 1:
        wr("No route_master relation found.\n")
        return
    elif nr > 1:
        wr("More than one route_master relations found: %s\n" \
          % (", ".join("[%s %s]" \
            % (osm.relid2url(r.id), r.id) for r in rm_rels)))
        return
    elif nr == 1:
        rel = rm_rels[0]
        wr("Relation: [%s %s]\n" % (osm.relid2url(rel.id), rel.id))
    memrefs = [m.ref for m in rel.members]
    refs_not_in_routes = [r for r in memrefs if r not in route_ids]
    if refs_not_in_routes:
        wr("route_master has extra members: %s\n" % (", ".join("[%s %s]" \
          % (osm.relid2url(r), r) for r in refs_not_in_routes)))
    routes_not_in_refs = [r for r in route_ids if r not in memrefs]
    if routes_not_in_refs:
        wr("Found matching routes not in route_master: %s\n" \
          % (", ".join("[%s %s]" \
            % (osm.relid2url(r), r) for r in routes_not_in_refs)))
    tags = rel.tags
    test_tag(tags, "route_master", mode)
    test_tag(tags, "ref", lineref)
    test_tag(tags, "name")
    test_tag(tags, "network", "HSL")
    #test_tag(tags, "operator")

    wr("")


# FIXME: Use templates for output
def print_linedict(ld, agency):
    """Print a info from a line dict from collect_line()"""
    lineref = ld["lineref"]
    mode = ld["mode"]
    modecolors = agency["modecolors"]
    wr("== %s ==" % lineref)
    rels = ld["rels"]
    if(len(rels) < 1):
        wr("No route relations found in OSM.")
        return
    relids = [r.id for r in rels]

    print_route_master(ld)

    alsoids = ld["alsoids"]
    if alsoids:
        wr("Extra routes in OSM with the same ref: %s\n" % \
          (", ".join("[%s %d]" % (osm.relid2url(r), r) for r in alsoids)))
    if len(rels) > 2:
        wr("More than 2 matching OSM routes found: %s.\n" % \
          (", ".join("[%s %d]" \
            % (osm.relid2url(rid), rid) for rid in relids)))
        wr("Giving up.")
        return
    codes = ld["codes"]
    osm2hsl = ld["osm2hsl"]
    hsl2osm = ld["hsl2osm"]
    if len(codes) != 2:
        wr("%d route pattern(s) in HSL data, matching may be wrong.\n" \
          % (len(codes)))
        for i in range(len(relids)):
            wr(" %s -> %s" % \
              (relids[i], "None" if osm2hsl[i] is None else codes[osm2hsl[i]]))
        for i in range(len(codes)):
            wr(" %s -> %s" % \
              (codes[i], "None" if hsl2osm[i] is None else relids[hsl2osm[i]]))
    wr("")

    id2hslindex = ld["id2hslindex"]
    htags = ld["htags"]
    interval_tags = ld["interval_tags"]
    hslshapes = ld["hslshapes"]
    for rel in rels:
        wr("'''Route [%s %s] %s'''\n" \
          % (osm.relid2url(rel.id), rel.id, rel.tags.get("name", "")))
        hsli = id2hslindex[rel.id]

        wr("'''Tags:'''\n")
        # name-tag gets a special treatment
        test_hsl_routename(rel.tags, htags["shortName"],  htags["longName"])
        # FIXME: network != agency always
        test_tag(rel.tags, "network", agency["name"])
        test_tag(rel.tags, "from")
        test_tag(rel.tags, "to")
        if modecolors[mode]:
            test_tag(rel.tags, "colour", modecolors[mode])
        test_tag(rel.tags, "color", badtag=True)
        if hsli is not None and interval_tags:
            itags = ld["hslitags"][hsli]
            for k in sorted(itags.keys()):
                test_tag(rel.tags, k, itags[k])

        if rel.tags.get("public_transport:version", "0") != "2":
            wr("Tag public_transport:version=2 not set in OSM route %s. Giving up." % (rel.id))
            continue

        if any(mem.role == 'forward' or mem.role == 'backward'
          for mem in rel.members):
            wr("OSM route(s) tagged with public_transport:version=2,")
            wr("but have members with 'forward' or 'backward' roles.")
            wr("Skipping shape, platform and stop tests.\n")
            continue

        wr("'''Shape:'''\n")
        if hsli is not None:
            tol = 30
            (shape, gaps) = osm.shape(rel)
            if gaps:
                wr("Route has '''gaps'''!\n")
            ovl = test_shape_overlap(shape, hslshapes[hsli], tol=tol)
            wr("Route [%s %s] overlap (tolerance %d m) with HSL pattern [%s %s] is '''%2.1f %%'''.\n" \
              % (osm.relid2url(rel.id), rel.id, tol, pattern2url(codes[hsli]),  codes[hsli], ovl*100.0))
        else:
            wr("Route %s overlap could not be calculated.\n" \
              % (rel.id))

        test_stop_positions(rel)

        hsli = id2hslindex[rel.id]
        # Platforms
        wr("'''Platforms:'''\n")
        hslplatforms = ld["hslplatforms"]
        if hsli is not None:
            osmplatform = osm.platforms(rel)
            hslplatform = hslplatforms[hsli]
            # FIXME: Add stop names to unified diffs after diffing, somehow
            #osmp = [p[2]+" "+p[3]+"\n" for p in osmplatform]
            #hslp = [str(p[2])+" "+str(p[3])+"\n" for p in hslplatform]
            osmp = [p[2]+"\n" for p in osmplatform]
            hslp = [p[2]+"\n" for p in hslplatform]
            diff = list(difflib.unified_diff(osmp, hslp, "OSM", "HSL"))
            if diff:
                outfile.writelines(" " + d for d in diff)
            else:
                wr(" => Identical platform sequences.\n")
        else:
            wr("Platforms could not be compared.")
        wr("")

    wr("")


def print_modedict(md):
    """Print modedict"""
    mode = md["mode"]
    agency = md["agency"]
    agencyurl = md["agencyurl"]
    osmdict = md["osmdict"]
    hsldict = md["hsldict"]
    hsl_localbus = md["hsl_localbus"]
    osm2dict = md["osm2dict"]

    osmlines = set(osmdict)
    hsllines = set(hsldict)
    hsl_locallines = set(hsl_localbus)
    wr("This is a comparison of OSM public transit route data with [%s %s] %s transit data (via [http://digitransit.fi digitransit.fi]) generated by a [https://github.com/tpikonen/taival script].\n" % (agencyurl, agency, mode))
    if mode == "subway":
        wr("See also [http://osmz.ru/subways/finland.html osmz.ru subway validator].\n")
    wr("= Summary of %s transit in %s region. =" % (mode, agency))
    wr("%d lines in OSM.\n" % len(osmlines))
    wr("%d lines in %s.\n" % (len(hsllines), agency))
    wr("")

    osmextra = osmlines.difference(hsllines)
    osmextra = list(osmextra.difference(hsl_locallines))
    osmextra.sort(key=linesortkey)
    wr("%d lines in OSM but not in HSL:" % len(osmextra))
    wr(" %s" % ", ".join(["%s (%s)" % \
        (x, ", ".join(["[%s %d]" % (osmdict[x][z], z+1) \
            for z in range(len(osmdict[x]))])) for x in osmextra ] ))
    wr("")

    hslextra = list(hsllines.difference(osmlines))
    hslextra.sort(key=linesortkey)
    wr("%d lines in HSL but not in OSM:" % len(hslextra))
    wr(" %s" % ", ".join(["[%s %s]" % (hsldict[x], x) for x in hslextra]))
    wr("")

    commons = list(hsllines.intersection(osmlines))
    commons.sort(key=linesortkey)
    wr("%d lines in both HSL and OSM." % len(commons))
    wr(" %s" % ", ".join(["%s (%s)" % \
        (x, ", ".join(["[%s %d]" % (osmdict[x][z], z+1) \
            for z in range(len(osmdict[x]))])) for x in commons] ))
    wr("")

    osm2lines = set(osm2dict)
    commons2 = list(hsllines.intersection(osm2lines))
    commons2.sort(key=linesortkey)
    wr("%d lines in both HSL and OSM with public_transport:version=2 tagging.\n" % len(commons2))
    wr(" %s" % ", ".join("[[#%s|%s]]" % (s, s) for s in commons2))
    wr("")

    if mode == "bus":
        lbuses = list(hsl_locallines)
        lbuses.sort(key=linesortkey)
        wr("= Local bus lines =")
        wr("%d bus routes with GTFS type 704 (lähibussi) in HSL." \
            % (len(lbuses)))
        wr(" %s" % ", ".join(["[%s %s]" % (hsl_localbus[x], x) \
            for x in lbuses] ))
        wr("")
        lcommons = list(hsl_locallines.intersection(osmlines))
        lcommons.sort(key=linesortkey)
        wr("%d normal bus routes in OSM with HSL local bus route number." \
            % (len(lcommons)))
        wr(" %s" % ", ".join(["%s (%s)" % \
            (x, ", ".join(["[%s %d]" % (osmdict[x][z], z+1) \
                for z in range(len(osmdict[x]))])) for x in lcommons ] ))
        wr("")
        osm_minibusdict = md["osm_minibusdict"]
        osm_minibuslines = list(osm_minibusdict)
        osm_minibuslines.sort(key=linesortkey)
        wr("%d route=minibus routes in OSM." % (len(osm_minibuslines)))
        wr(" %s" % ", ".join(["%s (%s)" % \
            (x, ", ".join(["[%s %d]" % (osm_minibusdict[x][z], z+1) \
                for z in range(len(osm_minibusdict[x]))])) \
                for x in osm_minibuslines ] ))
        wr("")

    wasroutes = md["wasroutes"]
    wr("= Old lines =")
    waslines = list(wasroutes)
    waslines.sort(key=linesortkey)
    wr("%d routes with type 'was:route=%s'." % (len(wasroutes), mode))
    wr(" %s" % ", ".join(["%s (%s)" % \
        (x, ", ".join(["[%s %d]" % (wasroutes[x][z], z+1) \
            for z in range(len(wasroutes[x]))])) for x in waslines] ))
    wr("")

    disroutes = md["disroutes"]
    dislines = list(disroutes)
    dislines.sort(key=linesortkey)
    wr("%d routes with type 'disused:route=%s'." % (len(disroutes), mode))
    wr(" %s" % ", ".join(["%s (%s)" % \
        (x, ", ".join(["[%s %d]" % (disroutes[x][z], z+1) \
            for z in range(len(disroutes[x]))])) for x in dislines] ))
    wr("")

    lines = md["lines"]
    wr("= Lines =")
    agdict = { "name" : agency, "modecolors" : md["modecolors"] }
    for l in lines:
        print_linedict(lines[l], agdict)


