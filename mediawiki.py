import difflib, sys
import osm
from util import *
from digitransit import pattern2url

outfile = None

style_problem = 'style="background-color: #ffaaaa" '
style_ok = 'style="background-color: #aaffaa" '
style_maybe = 'style="background-color: #eeee00" '
style_relstart = 'style="border-style: solid; border-width: 1px 1px 1px 3px" '

def wr(*args, **kwargs):
    kwargs["file"] = outfile
    print(*args, **kwargs)


def wr_if(s, **kwargs):
    """Write s if it's not empty."""
    if s:
        wr(s, **kwargs)

def test_tag(ts, key, value=None, badtag=False):
    """Test if a tag has a given value or just exists, if value=None.
    Return a string describing a problem, or empty string if no problems."""
    if not key in ts.keys():
        out = "Tag '''%s''' not set" % key
        if badtag:
            out = ""
        elif value is not None:
            out += " (should be '%s')." % value
        else:
            out += "."
        return out
    else:
        tval = ts[key]
        if badtag:
            out = "Probably '''mispelled''' tag '''%s''' with value '%s'." \
              % (key, tval)
        elif value is None:
            out = ""
        elif tval != value:
            out = "Tag '''%s''' has value '%s' (should be '%s')." \
              % (key, tval, value)
        else:
            out = ""
        return out


def test_hsl_routename(ts, lineref, longname):
    """Do a special test for the route name-tag.
    Return an empty string if ok, a string describing the problem if not."""
    # Reittiopas longName field sometimes has dangling hyphens, remove them.
    longname = longname[1:] if longname[0] == '-' else longname
    longname = longname[:-1] if longname[-1] == '-' else longname
    stops = hsl_longname2stops(longname)
    name1 = lineref + " " + "–".join(stops) # Use en dash as a separator
    stops.reverse()
    name2 = lineref + " " + "–".join(stops)
    tag = ts.get("name", "")
    out = ""
    if tag == "":
        out = "Tag '''name''' not set (should be either '%s' or '%s')." \
          % (name1, name2)
    elif tag != name1 and tag != name2:
        out = "Tag '''name''' has value '%s' (should be either '%s' or '%s')." \
          % (tag, name1, name2)
    return out


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
    wr_if(test_tag(tags, "route_master", mode), end='\n\n')
    wr_if(test_tag(tags, "ref", lineref), end='\n\n')
    wr_if(test_tag(tags, "name"), end='\n\n')
    wr_if(test_tag(tags, "network", "HSL"), end='\n\n')

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
        wr("Extra routes in OSM with the same ref: %s\n\n" % \
          (", ".join("[%s %d]" % (osm.relid2url(r), r) for r in alsoids)))
    if len(rels) > 2:
        wr("More than 2 matching OSM routes found: %s.\n" % \
          (", ".join("[%s %d]" \
            % (osm.relid2url(rid), rid) for rid in relids)))
        wr("Giving up.\n")
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
        wr_if(test_hsl_routename(rel.tags, htags["shortName"],  htags["longName"]), end='\n\n')
        # FIXME: network != agency always
        wr_if(test_tag(rel.tags, "network", agency["name"]), end='\n\n')
        wr_if(test_tag(rel.tags, "from"), end='\n\n')
        wr_if(test_tag(rel.tags, "to"), end='\n\n')
        if modecolors[mode]:
            wr_if(test_tag(rel.tags, "colour", modecolors[mode]), end='\n\n')
        wr_if(test_tag(rel.tags, "color", badtag=True), end='\n\n')
        if hsli is not None and interval_tags:
            itags = ld["hslitags"][hsli]
            for k in sorted(itags.keys()):
                wr_if(test_tag(rel.tags, k, itags[k]), end='\n\n')

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
            wr("Route [%s %s] overlap (tolerance %d m) with HSL pattern [%s %s] is '''%1.0f %%'''.\n" \
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


def cell_route_master(ld):
    """Return a (cell, details) tuple, where cell is contets of 'Master' cell
    in line table, possible problems are reported in details string."""

    lineref = ld["lineref"]
    mode = ld["mode"]
    rm_rels = ld["rm_rels"]
    route_ids = [r.id for r in ld["rels"]]

    nr = len(rm_rels)
    if nr < 1:
        return "No", ""
    elif nr > 1:
        cell = style_problem + "| more than 1"
        details = "'''Route master'''\nMore than one route_master relations found: %s\n" \
          % (", ".join("[%s %s]" \
            % (osm.relid2url(r.id), r.id) for r in rm_rels))
        return cell, details
    elif nr == 1:
        rel = rm_rels[0]
        cell = "[%s %s]" % (osm.relid2url(rel.id), rel.id)
    detlist= []
    memrefs = [m.ref for m in rel.members]
    refs_not_in_routes = [r for r in memrefs if r not in route_ids]
    if refs_not_in_routes:
        detlist.append("route_master has extra members: %s" % (", ".join("[%s %s]" \
          % (osm.relid2url(r), r) for r in refs_not_in_routes)))
    routes_not_in_refs = [r for r in route_ids if r not in memrefs]
    if routes_not_in_refs:
        detlist.append("Found matching routes not in route_master: %s" \
          % (", ".join("[%s %s]" \
            % (osm.relid2url(r), r) for r in routes_not_in_refs)))
    tags = rel.tags
    detlist.append(test_tag(tags, "route_master", mode))
    detlist.append(test_tag(tags, "ref", lineref))
    detlist.append(test_tag(tags, "name"))
    detlist.append(test_tag(tags, "network", "HSL"))
    if any(detlist): # prepend header
        details = "'''Route master:'''\n\n" \
          + "\n\n".join(s for s in detlist if s) + "\n\n"
        cell = style_problem + "| " + cell \
          + "[[#{} | more]]".format(ld["lineref"])
    else:
        details = ""
        cell = style_ok + "| " + cell
    return cell, details


def print_table(md):
    header = """{| class="wikitable"
|-
! style="border-style: none" |
! style="border-style: none" |
! style="border-style: none" |
! style="border-style: none" |
! style="border-style: solid; border-width: 1px 1px 1px 3px" colspan=5 | Direction 0
! style="border-style: solid; border-width: 1px 1px 1px 3px" colspan=5 | Direction 1"""
    subheader = """|-
! Line
! Master
! Extra
! Match
! style="border-style: solid; border-width: 1px 1px 1px 3px" | OSM
! HSL
! Tags
! Shape
! Platforms
! style="border-style: solid; border-width: 1px 1px 1px 3px" | OSM
! HSL
! Tags
! Shape
! Platforms"""
    footer = "|}"

    mode = md["mode"]
    wr("= PTv2 tagged HSL lines in OSM =\n")
    wr(header)
    linecounter = 0
    for line in md["lines"]:
        if linecounter % 20 == 0:
            wr(subheader)
        linecounter += 1
        ld = md["lines"][line]
        ld["details"] = ""
        # Line
        wr("|-")
        wr("| {}".format(line))
        # Master
        rm_cell, rm_details = cell_route_master(ld)
        if rm_details:
            ld["details"] += rm_details
        wr("| {}".format(rm_cell))
        # Extra
        if ld["alsoids"]:
            ld["details"] += "Extra routes in OSM with the same ref: %s\n\n" % \
              (", ".join("[%s %d]" % (osm.relid2url(r), r) for r in ld["alsoids"]))
            wr("| " + style_problem + " | [[#{} | yes]]".format(line))
        else:
            wr("| " + style_ok + " | No")
        # Match
        relids = [r.id for r in ld["rels"]]
        codes = ld["codes"]
        osm2hsl = ld["osm2hsl"]
        hsl2osm = ld["hsl2osm"]
        if len(ld["rels"]) > 2:
            ld["details"] += "More than 2 matching OSM routes found: %s.\n" % \
              (", ".join("[%s %d]" % (osm.relid2url(rid), rid) for rid in relids))
            ld["details"] += "Giving up.\n"
            wr("| " + style_problem + " | [[#{} | no]]".format(line))
            continue
        elif len(codes) != 2:
            ld["details"] += "%d route pattern(s) in HSL data, matching may be wrong.\n" \
              % (len(codes))
            for i in range(len(relids)):
                ld["details"] += " %s -> %s\n" % \
                  (relids[i], "None" if osm2hsl[i] is None else codes[osm2hsl[i]])
            for i in range(len(codes)):
                ld["details"] += " %s -> %s\n" % \
                  (codes[i], "None" if hsl2osm[i] is None else relids[hsl2osm[i]])
            wr("| " + style_maybe + " | [[#{} | maybe]]".format(line))
        else:
            wr("| " + style_ok + " | Uniq.")
        # Directions / OSM relations
        id2hslindex = ld["id2hslindex"]
        htags = ld["htags"]
        dirindex = 0
        for rel in ld["rels"]:
            dirdetails = ""
            # OSM
            wr("| " + style_relstart + "| [%s %s]" % (osm.relid2url(rel.id), rel.id))
            # HSL
            hsli = id2hslindex[rel.id]
            wr("| [%s %s]" % (pattern2url(codes[hsli]),  codes[hsli]))
            # Tags
            tdetlist = []
            # name-tag gets a special treatment
            tdetlist.append(test_hsl_routename(rel.tags, htags["shortName"],  htags["longName"]))
            # FIXME: network != agency always
            tdetlist.append(test_tag(rel.tags, "network", md["agency"]))
            tdetlist.append(test_tag(rel.tags, "from"))
            tdetlist.append(test_tag(rel.tags, "to"))
#            if md["modecolors"][mode]:
#                tdetlist.append(test_tag(rel.tags, "colour", md["modecolors"][mode]))
            tdetlist.append(test_tag(rel.tags, "color", badtag=True))
            if hsli is not None and md["interval_tags"]:
                itags = ld["hslitags"][hsli]
                for k in sorted(itags.keys()):
                    tdetlist.append(test_tag(rel.tags, k, itags[k]))

            if rel.tags.get("public_transport:version", "0") != "2":
                dirdetails += "'''Tags:\n\n" + "\n\n".join([s for s in tdetlist if s]) + "\n\n"
                dirdetails += "Tag public_transport:version=2 not set in OSM route %s. Giving up.\n\n" % (rel.id)
                wr("| " + style_problem + " | [[#{} | no PTv2]]".format(line))
                continue
            elif any(mem.role == 'forward' or mem.role == 'backward'
              for mem in rel.members):
                dirdetails += "'''Tags:\n\n" + "\n\n".join([s for s in tdetlist if s]) + "\n\n"
                dirdetails += "OSM route(s) tagged with public_transport:version=2,"
                dirdetails += "but have members with 'forward' or 'backward' roles."
                dirdetails += "Skipping shape and platform tests.\n\n"
                wr("| " + style_problem + " | [[#{} | PTv1]]".format(line))
                wr("| " + style_problem + " | N/A")
                wr("| " + style_problem + " | N/A")
                continue
            elif any(tdetlist):
                dirdetails += "'''Tags:'''\n\n" + "\n\n".join([s for s in tdetlist if s]) + "\n\n"
                wr("| " + style_problem + " | [[#{} | info]]".format(line))
            else:
                wr("| " + style_ok + " | OK")
            # Shape
            sdetlist = []
            if hsli is not None:
                tol = 30
                (shape, gaps) = osm.shape(rel)
                ovl = test_shape_overlap(shape, ld["hslshapes"][hsli], tol=tol)
                if gaps:
                    sdetlist.append("Route has '''gaps'''!")
                    sdetlist.append("Route [%s %s] overlap (tolerance %d m) with HSL pattern [%s %s] is '''%1.0f %%'''." \
                      % (osm.relid2url(rel.id), rel.id, tol, pattern2url(codes[hsli]),  codes[hsli], ovl*100.0))
                if gaps:
                    wr("| " + style_problem + " | [[#{} | gaps]]".format(line))
                elif ovl <= 0.90:
                    wr("| " + style_problem + " | %1.0f%%" % (ovl*100.0))
                elif ovl <= 0.95:
                    wr("| " + style_maybe + " | %1.0f%%" % (ovl*100.0))
                else:
                    wr("| " + style_ok + " | %1.0f%%" % (ovl*100.0))
            else:
                sdetlist.append("Route %s overlap could not be calculated.\n" \
                  % (rel.id))
                wr("| " + style_problem + " | [[#{} | error]]".format(line))
            if any(sdetlist):
                dirdetails += "'''Shape:'''\n\n" + "\n\n".join(sdetlist) + "\n\n"

            # Platforms TODO
            wr("| " + style_ok + " | OK")
#            hsli = id2hslindex[rel.id]
#            # Platforms
#            wr("'''Platforms:'''\n")
#            hslplatforms = ld["hslplatforms"]
#            if hsli is not None:
#                osmplatform = osm.platforms(rel)
#                hslplatform = hslplatforms[hsli]
#                # FIXME: Add stop names to unified diffs after diffing, somehow
#                #osmp = [p[2]+" "+p[3]+"\n" for p in osmplatform]
#                #hslp = [str(p[2])+" "+str(p[3])+"\n" for p in hslplatform]
#                osmp = [p[2]+"\n" for p in osmplatform]
#                hslp = [p[2]+"\n" for p in hslplatform]
#                diff = list(difflib.unified_diff(osmp, hslp, "OSM", "HSL"))
#                if diff:
#                    outfile.writelines(" " + d for d in diff)
#                else:
#                    wr(" => Identical platform sequences.\n")
#            else:
#                wr("Platforms could not be compared.")
#            wr("")
            if dirdetails:
                dirdetails = "'''Direction {}'''\n\n".format(dirindex) + dirdetails
                ld["details"] += dirdetails
            dirindex += 1
    wr(footer)
    wr("\n")

    # details
    if any(ld["details"] for ld in md["lines"].values()):
        wr("== Details on differences ==\n")
    else:
        return
    for ld in md["lines"].values():
        if ld["details"]:
            wr("=== {} ===".format(ld["lineref"]))
            wr(ld["details"])

