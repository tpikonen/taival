#!/usr/bin/env python3
import sys, datetime, gpxpy.gpx, argparse, logging, pickle
import digitransit, osm
import mediawiki as mw
from util import *

hsl_modecolors = { "bus": "#007AC9",
    "tram":     "#00985F",
    "train":    "#8C4799",
    "subway":   "#FF6319",
    "ferry":    "#00B9E4",
    "aerialway": None,
    "monorail": None,
    "trolleybus": None
}
hsl_peakhours = [(7, 9), (15,18)]
# HSL night services start at 23, but use midnight to avoid overlap with
# normal services.
hsl_nighthours = [(0, 5)]
hsl = digitransit.Digitransit("HSL", \
        "https://api.digitransit.fi/routing/v1/routers/hsl/index/graphql", \
        hsl_modecolors, hsl_peakhours, hsl_nighthours)

logging.basicConfig(level=logging.INFO,
    format="[%(asctime)s.%(msecs)03d] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")

log = logging.getLogger(__name__)


def write_gpx(latlon, fname, waypoints=[]):
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)
    gpx_segment = gpxpy.gpx.GPXTrackSegment()
    gpx_track.segments.append(gpx_segment)
    for ll in latlon:
        gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(ll[0], ll[1]))
    for w in waypoints:
        gpx.waypoints.append(gpxpy.gpx.GPXWaypoint(w[0], w[1], name=w[2],
                                                   description=w[3]))
    with open(fname, "w") as ff:
        ff.write(gpx.to_xml())


def digitransit2gpx(dt, lineref, mode="bus"):
    """Write gpx files for given lineref from digitransit API data."""
    log.debug("Calling dt.codes")
    codes = dt.codes(lineref, mode)
    for c in codes:
        log.debug("    Calling dt.shape")
        (dirid, latlon) = dt.shape(c)
        log.debug("    Calling dt.platforms")
        stops = dt.platforms(c)
        fname = "%s_%s_%s_%d.gpx" % (lineref, dt.agency, c, dirid)
        write_gpx(latlon, fname, waypoints=stops)
        print(fname)
    if not codes:
        log.error("Line '%s' not found in %s." % lineref, dt.agency)


def route2gpx(rel, fname):
    """Write a gpx-file fname from an overpy relation containing
    an OSM public_transport:version=2 route."""
    log.debug("Calling osm.shape")
    latlon = osm.route_shape(rel)[0]
    log.debug("Calling osm.platforms")
    waypts = osm.route_platforms(rel)
    write_gpx(latlon, fname, waypoints=waypts)


def osm2gpx(lineref, mode="bus"):
    log.debug("Calling osm.rels_v2")
    rels = osm.rels_v2(lineref, mode)
    if len(rels) > 0:
        for i in range(len(rels)):
            fn = "%s_osm_%d.gpx" % (lineref, i)
            route2gpx(rels[i], fn)
            print(fn)
    else:
        log.error("Line '%s' not found in OSM PTv2 relations." % lineref)


def collect_interval_tags(code):
    """Return interval tags for a pattern code determined from HSL data
    for peak and normal hours for weekdays (monday), saturday and sunday.
    Intervals are converted from arrival data."""
    # Get interval tags from API
    today = datetime.date.today()
    delta = (5 + 7 - today.weekday()) % 7 # Days to next saturday
    tags = {}
    daynames = ["saturday", "sunday", None] # weekdays (monday) is the default
    for i in range(3):
        day = (today + datetime.timedelta(days=delta+i)).strftime("%Y%m%d")
        (norm, peak, night) = arrivals2intervals(\
            hsl.arrivals_for_date(code, day), hsl.peakhours, hsl.nighthours)
        tagname = "interval" + (":" + daynames[i] if daynames[i] else "")
        if (len(norm) + len(peak) + len(night)) == 0:
            tags[tagname] = "no_service"
        else:
            # FIXME: Maybe combine norm and peak if peak is short enough?
            # Only tag if there are more than 2 intervals, i.e.
            # at least 3 arrivals in a period.
            if len(norm) > 1:
                med_norm = norm[len(norm)//2]
                tags[tagname] = str(med_norm)
                if len(peak) > 1:
                    med_peak = peak[len(peak)//2]
                    # Only add interval:peak tag if it's significantly smaller.
                    if med_peak <= 0.8* med_norm:
                        tags[tagname + ":peak"] = str(med_peak)
            if len(night) > 1:
                tags[tagname + ":night"] = str(night[len(night)//2])
                if not norm:
                    tags[tagname] = "no_service"
    itmp = tags.get("interval", "1")
    interval = int(itmp) if itmp.isdigit() else 1
    itmp = tags.get("interval:saturday", "1")
    isat = int(itmp) if itmp.isdigit() else 1
    itmp = tags.get("interval:sunday", "1")
    isun = int(itmp) if itmp.isdigit() else 1
    itmp = tags.get("interval:night", "1")
    inight = int(itmp) if itmp.isdigit() else 1
    itmp = tags.get("interval:saturday:night", "1")
    isatnight = int(itmp) if itmp.isdigit() else 1
    itmp = tags.get("interval:sunday:night", "1")
    isunnight = int(itmp) if itmp.isdigit() else 1
    # Remove weekend tags if they are not significantly different
    if abs(isat - interval)/interval < 0.2 \
      and tags.get("interval:saturday", "") != "no_service":
        tags.pop("interval:saturday", 0)
        tags.pop("interval:saturday:peak", 0)
    if abs(isun - interval)/interval < 0.2 \
      and tags.get("interval:sunday", "") != "no_service":
        tags.pop("interval:sunday", 0)
        tags.pop("interval:sunday:peak", 0)
    if abs(isatnight - inight)/inight < 0.2 \
      and tags.get("interval:saturday:night", "") != "no_service":
        tags.pop("interval:saturday:night", 0)
    if abs(isunnight - inight)/inight < 0.2 \
      and tags.get("interval:sunday:night", "") != "no_service":
        tags.pop("interval:sunday:night", 0)
    return tags


def match_shapes(shapes1, shapes2):
    """Determine a mapping from one set of shapes to another, based on
    geometry. Return permutation indices for both directions."""
    if len(shapes1) > len(shapes2):
        swap = True
        s1 = shapes2
        s2 = shapes1
    else:
        swap = False
        s1 = shapes1
        s2 = shapes2
    m1to2 = [None]*len(s1)
    m2to1 = [None]*len(s2)
    for i in range(len(s1)):
        if not s1[i]: # Handle empty shape
            m1to2[i] = 0
            break
        mind = 1.0e10
        minind = 0
        cbeg = s1[i][0]
        cend = s1[i][-1]
        for j in range(len(s2)):
            #d = min(ldist2(cbeg, s2[j][0]), ldist2(cend, s2[j][-1]))
            d = ldist2(cbeg, s2[j][0]) + ldist2(cend, s2[j][-1])
            if d < mind:
                mind = d
                minind = j
        m1to2[i] = minind
    for i in range(len(m1to2)):
        m2to1[m1to2[i]] = i
#    if any(v is None for v in m1to2 + m2to1):
#        print("(mapping is not a bijection)")
    if swap:
        return (m2to1, m1to2)
    else:
        return (m1to2, m2to1)


def collect_line(lineref, mode="bus", interval_tags=False):
    """Report on differences between OSM and HSL data for a given line."""
    ld = {} # line dict
    ld["lineref"] = lineref
    ld["mode"] = mode
    ld["interval_tags"] = interval_tags
    log.debug("Calling osm.rels")
    rels = osm.rels(lineref, mode)
    if(len(rels) < 1):
        log.debug("No route relations found in OSM.")
        return ld
    allrelids = [r.id for r in rels]
    rels = [r for r in rels \
            if (r.tags.get("public_transport:version", "") == "2") and
                (r.tags.get("network", "") == "HSL"
                or r.tags.get("network", "") == "Helsinki"
                or r.tags.get("network", "") == "Espoo"
                or r.tags.get("network", "") == "Vantaa")]
    relids = [r.id for r in rels]
    ld["rels"] = rels

    log.debug("Calling osm.route_master")
    ld["rm_rels"] = osm.route_master(relids)

    log.debug("Found OSM route ids: %s\n" % \
      (", ".join("[%s %d]" % (osm.relid2url(rid), rid) for rid in relids)))
    alsoids = [r for r in allrelids if r not in relids]
    ld["alsoids"] = alsoids

    log.debug("Calling hsl.tags")
    htags = hsl.tags(lineref)
    ld["htags"] = htags
#    codes = hsl.codes_after_date(lineref, \
#                datetime.date.today().strftime("%Y%m%d"), mode)
#    codes = hsl.codes_longest_per_direction(lineref, mode)
    log.debug("Calling codes_longest_after_date")
    codes = hsl.codes_longest_after_date(lineref, \
                datetime.date.today().strftime("%Y%m%d"), mode)
    ld["codes"] = codes
    log.debug("Found HSL pattern codes: %s\n" %
        (", ".join("[%s %s]" % (digitransit.pattern2url(c), c) for c in codes)))
#    # Use just the ':01' route variant
#    cfilt = [c for c in codes if (len(c) - c.rfind(":01")) == 3]
#    if len(cfilt) >= len(rels):
#        codes = cfilt
#        log.debug("Using just first route variants: %s\n" % (str(codes)))

    # Mapping
    # FIXME: Duplicate call to osm.route_shape() in route checking loop.
    osmshapes = [osm.route_shape(rel)[0] for rel in rels]
    hslshapes = [hsl.shape(c)[1] for c in codes]
    (osm2hsl, hsl2osm) = match_shapes(osmshapes, hslshapes)
    id2hslindex = {}
    for i in range(len(relids)):
        id2hslindex[relids[i]] = osm2hsl[i]
    ld["osmshapes"] = osmshapes
    ld["hslshapes"] = hslshapes
    ld["id2hslindex"] = id2hslindex
    ld["osm2hsl"] = osm2hsl
    ld["hsl2osm"] = hsl2osm
    # Fill hslplatforms hslitags only for pattern codes which match OSM route
    hslplatforms = [None]*len(codes)
    hslitags = [None]*len(codes)
    for rel in rels:
        hsli = id2hslindex[rel.id]
        if hsli is not None:
            hslplatforms[hsli] = [ p if p[2] else (p[0],p[1],"<no ref in HSL>",p[3])
                for p in hsl.platforms(codes[hsli]) ]
            if interval_tags:
                hslitags[hsli] = collect_interval_tags(codes[hsli])
    ld["hslplatforms"] = hslplatforms
    if interval_tags:
        ld["hslitags"] = hslitags
    return ld


def collect_mode(mode="bus", interval_tags=False):
    """Collect data for a given mode from APIs, call collect_line for
    all discovered lines."""
    md = {}
    md["mode"] = mode
    md["interval_tags"] = interval_tags
    # TODO: Replace HSL with agency var everywhere.
    agency = "HSL"
    agencyurl = "https://www.hsl.fi/"
    md["agency"] = agency
    md["agencyurl"] = agencyurl
    md["modecolors"] = hsl_modecolors

    osmdict = osm.all_linerefs(mode)
    hsldict = hsl.all_linerefs(mode)
    hsl_localbus = hsl.taxibus_linerefs(mode)
    osm2dict = osm.ptv2_linerefs(mode)
    wasroutes = osm.was_routes(mode)
    disroutes = osm.disused_routes(mode)
    md["osmdict"] = osmdict
    md["hsldict"] = hsldict
    md["hsl_localbus"] = hsl_localbus
    md["osm2dict"] = osm2dict
    md["wasroutes"] = wasroutes
    md["disroutes"] = disroutes

    if mode == "bus":
        osm_minibusdict = osm.all_linerefs(mode="minibus")
        md["osm_minibusdict"] = osm_minibusdict

    osm2lines = set(osm2dict)
    hsllines = set(hsldict)
    commons2 = list(hsllines.intersection(osm2lines))
    commons2.sort(key=linesortkey)
    lines = {}
    for line in commons2:
        ld = collect_line(line, mode, interval_tags)
        lines[line] = ld
    md["lines"] = lines
    return md


def sub_gpx(args):
    log.info("Processing line %s, mode '%s'" % (args.line, args.mode))
    osm2gpx(args.line, args.mode)
    digitransit2gpx(hsl, args.line, args.mode)


def sub_osmxml(args):

    def write_xml(fname, ids, htags, mode, reverse=False):
        with open(fname, "w") as ff:
            for i in ids:
                ff.write("    <member type='node' ref='%d' role='platform' />\n" % i)
            stopnames = hsl_longname2stops(htags["longName"])
            if reverse:
                stopnames.reverse()
            ff.write("    <tag k='name' v='%s' />\n" \
                % (htags["shortName"] + " " + "–".join(stopnames)))
            ff.write("    <tag k='ref' v='%s' />\n" % htags["shortName"])
            ff.write("    <tag k='network' v='HSL' />\n")
            ff.write("    <tag k='route' v='%s' />\n" % mode)
            ff.write("    <tag k='type' v='route' />\n")
            ff.write("    <tag k='public_transport:version' v='2' />\n")

    log.info("Processing line %s, mode '%s'" % (args.line, args.mode))
    log.debug("Calling hsl.codes")
    codes = hsl.codes(args.line, args.mode)
    log.debug("Calling hsl.tags")
    htags = hsl.tags(args.line)
    for c in codes:
        log.debug("Pattern code %s" % c)
        # reverse stops string if direction code is odd
        reverse = (int(c.split(":")[2]) % 2) == 1
        log.debug("   Calling hsl.platforms")
        stops = [p[2] for p in hsl.platforms(c)]
        fname = "%s_%s_%s.osm" % (args.line, hsl.agency, c)
        log.debug("   Calling osm.stops_by_refs")
        ids = osm.stops_by_refs(stops, args.mode)
        write_xml(fname, ids, htags, args.mode, reverse)
        print(fname)
    if not codes:
        print("Line '%s' not found in %s." % lineref, hsl.agency)


def output_dict(d, args):
    """Write output from dict"""
    def get_output(args):
        if args.output == '-':
            out = sys.stdout
        else:
            out = open(args.output, "w")
        return out

    out = None
    if args.format == "mediawiki":
        out = get_output(args)
        mw.outfile = out
        if "lineref" in d.keys():
            mw.print_linedict(d)
        else:
#            mw.print_modedict(d)
            mw.report_tabular(d)
    elif args.format == "pickle":
        out = get_output(args)
        pickle.dump(d, out)
    else:
        log.error("Unknown output format '%s'" % args.output)
    if out and out != sys.stdout:
        out.close()


def sub_line(args):
    ld = collect_line(args.line, args.mode, args.interval_tags)
    output_dict(ld, args)


def sub_report(args):
    md = collect_mode(mode=args.mode, interval_tags=args.interval_tags)
    output_dict(md, args)


def sub_format(args):
    with open(args.file, 'rb') as f:
        d = pickle.load(f)
    output_dict(d, args)


#def sub_fullreport(args):
#    pass


# TODO: Add sub_stops(args) for creating a report on stops
# List of stop code prefixes from gtfs:
# csvtool namedcol stop_code stops.txt| tail -n+2 | grep -o '^[^0-9]*' | sort -u
# TODO: Test ref:findr tag on stops test_tag(rel.tags, "ref:findr")

if __name__ == '__main__' and '__file__' in globals ():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', '-v', action='version', version='0.0.1')
    parser.set_defaults(func=lambda _: print(parser.format_usage()))
    subparsers = parser.add_subparsers(help='sub-command -h for help')

    parser_gpx = subparsers.add_parser('gpx', help='Output gpx files for given line.')
    parser_gpx.add_argument('line', metavar='<lineid>',
        help='Line id to process.')
    parser_gpx.add_argument('mode', nargs='?', metavar='<mode>', default="bus",
        help='Transport mode: train, subway, tram, bus (default) or ferry')
    parser_gpx.set_defaults(func=sub_gpx)

    parser_osmxml = subparsers.add_parser('osmxml', help='Output OSM XML snippets with stops and some tags for a given line.')
    parser_osmxml.add_argument('line', metavar='<lineid>',
        help='Line id to process.')
    parser_osmxml.add_argument('mode', nargs='?', metavar='<mode>',
        default="bus",
        help='Transport mode: train, subway, tram, bus (default) or ferry')
    parser_osmxml.set_defaults(func=sub_osmxml)

    parser_line = subparsers.add_parser('line', help='Create a report for a given line.')
    parser_line.add_argument('--interval-tags', '-i', action='store_true',
        dest='interval_tags', help='Also report on "interval*" tags')
    parser_line.add_argument('line', metavar='<lineid>',
        help='Line id to report on.')
    parser_line.add_argument('mode', nargs='?', metavar='<mode>', default="bus",
        help='Transport mode: train, subway, tram, bus (default) or ferry')
    parser_line.add_argument('--output', '-o', metavar='<output-file>',
        dest='output', default='-', help='Direct output to file (default stdout)')
    parser_line.add_argument('--format', '-f', metavar='<format>',
        dest='format', default='mediawiki',
        help='Output format: mediawiki (default), pickle')
    parser_line.set_defaults(func=sub_line)

    parser_report = subparsers.add_parser('report',
        help='Report on all lines for a given mode.')
    parser_report.add_argument('--interval-tags', '-i', action='store_true',
        dest='interval_tags', help='Also report on "interval*" tags')
    parser_report.add_argument('mode', nargs='?', metavar='<mode>',
        default="bus",
        help='Transport mode: train, subway, tram, bus (default) or ferry')
    parser_report.add_argument('--output', '-o', metavar='<output-file>',
        dest='output', default='-', help='Direct output to file (default stdout)')
    parser_report.add_argument('--format', '-f', metavar='<format>',
        dest='format', default='mediawiki',
        help='Output format: mediawiki (default), pickle')
    parser_report.set_defaults(func=sub_report)

    parser_format = subparsers.add_parser('format',
        help='Format and output previously collected data from pickle format.')
    parser_format.add_argument('file', nargs='?', metavar='<pickle-file>',
        help='Input file')
    parser_format.add_argument('--output', '-o', metavar='<output-file>',
        dest='output', default='-', help='Direct output to file (default stdout)')
    parser_format.add_argument('--format', '-f', metavar='<format>',
        dest='format', default='mediawiki',
        help='Output format: mediawiki (default), pickle')
    parser_format.set_defaults(func=sub_format)

#    parser_fullreport = subparsers.add_parser('fullreport',
#        help='Create a report for all lines.')
#    parser_fullreport.set_defaults(func=sub_fullreport)

    parser_help = subparsers.add_parser('help',
        help="Show help for a subcommand")
    parser_help.add_argument('subcmd', metavar='<subcommand>', nargs='?',
        default='taival', help="Print help for this subcommand.")
    def helpfun(arx):
        if arx.subcmd == 'taival':
            parser.print_help()
        else:
            subparsers.choices[args.subcmd].print_help()
    parser_help.set_defaults(func=helpfun)

    args = parser.parse_args()
    #sys.exit(1)
    args.func(args)
